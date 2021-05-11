import math
import json
from datetime import datetime as time
from poseParser.socket_class import SocketManager

import numpy as np

# Confidence score required to validate a keypoint set.
MINIMUM_CONFIDENCE = 0

# Mapping of parts to array as per posenet keypoints.
PART_MAP = {
    0: "nose",
    1: "leftEye",
    2: "rightEye",
    3: "leftEar",
    4: "rightEar",
    5: "leftShoulder",
    6: "rightShoulder",
    7: "leftElbow",
    8: "rightElbow",
    9: "leftWrist",
    10: "rightWrist",
    11: "leftHip",
    12: "rightHip",
    13: "leftKnee",
    14: "rightKnee",
    15: "leftAnkle",
    16: "rightAnkle"
}  # A 'timestamp' field is added to dictionary when parsed.


class PoseParserNode:
    """
    ROSpy Node for parsing data from posenet. Adds timestamp to notate when message was received.
    """
    _instance = None
    # Options for default metric are any one string from the following:
    # "demo_metric", "offset_midpoints", "centroid", "average_speed_of_points", "positional_demo", "centroid_coords"
    DEFAULT_METRIC = "offset_midpoints"
    metrics = None
    metric_functions = None
    socket_manager = None
    username = ""
    # TODO - Joe, this sets logging to files on and off, in the user study set it to false.
    log_data = False

    def __init__(self):
        raise TypeError("Class is singleton, call instance() not init")

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            # TODO - Here we set history_length to none to ensure list is never pruned
            cls.metrics = PoseMetrics(history_length=None)
            cls.metric_functions = PoseMetrics.metric_list.keys()
        return cls._instance

    def convert_to_dictionary(self, data):
        """
        Takes data recorded from posenet and converts it into a python dictionary with sensible keys.

        Args:
            data(list): A list sent from posenet.

        Returns:
            dict: A python dictionary containing pose data for each keypoint including (x, y)
                locations and confidence score.
        """
        pose_dict = {}
        for i in range(0, len(data)):
            # Use posenet part mapping to label positions from list.
            pose_dict[PART_MAP[i]] = {
                "position": (float(data[i]["position"]["x"]), float(data[i]["position"]["y"])),
                "score": float(data[i]["score"])
            }
        pose_dict["timestamp"] = time.now()
        PoseParserNode.metrics.register_keypoints(pose_dict)
        return pose_dict

    def callback(self, data):
        """
        Callback serves as a function entry point for all socket calls for setting
        recording logs, usernames and obtaining pose data
        """
        # points_data = json.loads(data)

        # print('the data type is', type(data))
        dict_name = list(data.keys())
        # TODO - Not ideal, but split functions based on first key in dict
        if dict_name[0] == "poser" and self.log_data:
            points_data = data["poser"]
            keypoints = self.convert_to_dictionary(points_data["keypoints"])

            # print('the data type is now', type(keypoints))
            # if self.DEFAULT_METRIC in PoseParserNode.metric_functions:
            trajectory_points = PoseParserNode.metrics.execute_metric(self.DEFAULT_METRIC, keypoints, 'leftWrist', 'rightWrist')
        #     if trajectory_points is not None:
        #         self.publisher(trajectory_points)
            self.publisher(trajectory_points)
        elif dict_name[0] == "username":
            self.username = data["username"]
            self.metrics.load_history(self.username)
            print('loading user data for',self.username)
        elif dict_name[0] == "flightmode":
            # If key in dictionary is flightmode, save flightmode to check state and
            # decide on starting or stopping logging
            flightmode = data["flightmode"]
            if flightmode == "follow":
                self.log_data = True
            else:
                self.log_data = False
                self.metrics.save_history(self.username)
                print('saving user data for', self.username)

    def listener(self):
        """
        Creates and starts the socket server.
        """
        if self.socket_manager is None:
            self.socket_manager = SocketManager(self, server=True)
        self.socket_manager.listen()

    def got_message(self, address, message):
        """
        Callback function for when a message is received over sockets.

        Args:
            address: The address of the sender.
            message: The message received.
        """
        self.callback(message)
        # print(message)
        return "DONE"

    def publisher(self, trajectory_parameters):
        """
        Generates and publishes a MultiDOFJointTrajectory message from inputs to publisher topic for simulator.

        Args:
            trajectory_parameters(dict): A dictionary containing all data fields required to build a Trajectory message.
        """
        # print(trajectory_parameters["proximity"]) # 10.132.69.52
        self.socket_manager.send_message(port=5050, message=(trajectory_parameters["proximity"]))

    def test_metrics(self, keypoints):
        """
        Calls all three advanced metrics with the keypoint data for viewing logs of responses for metrics.
        Uncommenting the print lines in these metrics enables the console log functionality.
        This is more of an example of how to call metrics than functional code.
        """
        print(PoseParserNode.metrics.execute_metric("offset_midpoints", keypoints, "leftEye", "rightEye"))
        print(PoseParserNode.metrics.execute_metric("centroid", keypoints, ["leftEye", "rightEye"]))
        print(PoseParserNode.metrics.execute_metric("average_speed_of_points", keypoints, ["leftEye", "rightEye"]))


class PoseMetrics:
    """
    Container class for pose metrics.
    Metrics designed to be called external to this class must conform to the function layout that follows even if the
    metric does not require them as the convenience method selector expects 3 arguments regardless of if they are used
    or not.  "def metric(dict, list, list)"
    The variable dictionary "metric_list" can contain a string name and function value to ease calling of metrics.
    """
    # Default Focus for the average_speed metric
    DEFAULT_FOCUS_POINT_1 = "leftEye"
    DEFAULT_FOCUS_POINT_2 = "rightEye"

    # Default focus for angle threshold demo.
    ANGLE_THRESHOLD = 15
    previous_angle = None
    POSITION_BASE = "rightShoulder"
    POSITION_OUTER = "rightWrist"

    # Length of list to calculate averages from history.
    DEFAULT_HISTORY_LENGTH = 50

    # Used for demo_metric.
    high = None

    # Default values for metric return properties.
    default_x = 0.0
    default_y = 0.0
    default_z = 1.0
    default_rotation_x = 0.0
    default_rotation_y = 0.0
    default_rotation_z = 0.0
    default_rotation_w = 1.0
    default_velocity_x = 1.0
    default_velocity_y = 1.0
    default_velocity_z = 1.0
    default_velocity_angular_x = 1.0
    default_velocity_angular_y = 1.0
    default_velocity_angular_z = 1.0
    default_acceleration_linear_x = 1.0
    default_acceleration_linear_y = 1.0
    default_acceleration_linear_z = 1.0
    default_acceleration_angular_x = 1.0
    default_acceleration_angular_y = 1.0
    default_acceleration_angular_z = 1.0

    # Variables for maintaining a history of past data for use in metric calculations.
    history = [{}]
    centroid_history = [{}]
    history_length = 0

    def __init__(self, history_length=DEFAULT_HISTORY_LENGTH):
        PoseMetrics.history_length = history_length

    def register_keypoints(self, keypoints):
        """
        Takes a dictionary of parsed pose data and adds it to the history list with timestamp.
        Ideally, should only be called once, immediately after keypoints are parsed.

        Args:
            keypoints(dict): Latest set of pose data as parsed dictionary.

        """
        data = {}
        try:
            for point in keypoints:
                if point in PART_MAP.values():
                    if keypoints[point]["score"] < MINIMUM_CONFIDENCE:
                        data[point] = None
                    else:
                        data[point] = keypoints[point]["position"]
                elif point == "timestamp":
                    data["timestamp"] = keypoints[point]
            PoseMetrics.history.insert(0, data.copy())
            # Log history of calculated centroid.
            self.centroid(keypoints)
            # Prune list if it gets too long
            if self.history_length is not None:
                if len(PoseMetrics.history) > self.history_length:
                    PoseMetrics.history.pop()
                if len(PoseMetrics.centroid_history) > self.history_length:
                    PoseMetrics.centroid_history.pop()
            return True
        except KeyError as e:
            print("Exception occured\n%s\nKeyPoints passed in:\n%s" % (str(e), str(keypoints)))
            return False

    def midpoint(self, keypoints, point_1_name=DEFAULT_FOCUS_POINT_1, point_2_name=DEFAULT_FOCUS_POINT_2):
        """
        Finds the middle point between 2 x,y locations. Default points are left and right wrists.

        Args:
            keypoints(dict): A dictionary of all pose keypoints.
            point_1_name(str): Name of keypoint 1 to use in metric.
            point_2_name(str): Name of keypoint 2 to use in metric.

        Returns:
            dict: The midpoint x,y given two points and a score of between 0-1 based on proximity
                to point 1 and 2 respectively, formatted into generic dictionary as expected by parser node.
        """

        if point_1_name is None:
            point_1_name = self.DEFAULT_FOCUS_POINT_1
        if point_2_name is None:
            point_2_name = self.DEFAULT_FOCUS_POINT_2

        point_1 = keypoints[point_1_name]["position"]
        point_2 = keypoints[point_2_name]["position"]
        x_diff = abs(point_1[0] - point_2[0])
        y_diff = abs(point_1[1] - point_2[1])
        midpoint_x = max(point_1[0], point_2[0]) - (x_diff / 2)
        midpoint_y = max(point_1[1], point_2[1]) - (y_diff / 2)
        proximity_x = abs((midpoint_x - point_1[0]) / x_diff)
        proximity_y = abs((midpoint_y - point_1[1]) / x_diff)

        # Uncomment the following to have results logged to the console.
        # print("Offset Mid\nPoint 1: %s @ %s, Point 2: %s @ %s, Mid-Point: %s, Proximity Score: %s" %
        #               (point_1_name, str(point_1), point_2_name, str(point_2), str((midpoint_x, midpoint_y)),
        #                str((proximity_x + proximity_y) / 2)))

        return self.create_return_dictionary(x=midpoint_x, y=midpoint_y,
                                             proximity_value=(proximity_x + proximity_y) / 2)

    def centroid(self, keypoints, point_list1=None, point_list2=None):
        """
        Returns the mean x,y coordinates as a midpoint from a list of specified point names.
        Defaults to entire part map.

        Args:
            keypoints(dict): A dictionary of all pose keypoints.
            point_list1(list[str]): A list of keypoint position names present in the part map.
            point_list2: Not Used.

        Returns:
            dict: x,y coordinates of the calculated centroid midpoint, formatted into generic dictionary
                as expected by parser node.
        """
        if point_list1 is None:
            point_list1 = PART_MAP.values()
        x_list = []
        y_list = []
        for point in point_list1:
            if point in PART_MAP.values():
                x_list.append(keypoints[point]["position"][0])
                y_list.append(keypoints[point]["position"][1])
        midpoint = (float(np.mean(x_list)), float(np.mean(y_list)))
        PoseMetrics.centroid_history.insert(0, {"midpoint": {"position": (midpoint[0], midpoint[1])},
                                         "timestamp": time.now()})

        # Uncomment the following to have results logged to the console.
        # print("Centroid\nMidpoint: %s" % str(midpoint))

        return self.create_return_dictionary(x=midpoint[0], y=midpoint[1])

    def centroid_movement_speed(self, unused1=None, unused2=None, unused3=None):
        """
        Returns the average speed for the centroid location according to history list. Arguments are not used
        and only exist to conform to the metric function dictionary for creating generic calls.

        Args:
            unused1: Not Used.
            unused2: Not Used.
            unused3: Not Used.

        Returns:
            dict: The average movement speed of the calculated centroid, formatted into generic dictionary as
                expected by parser node.
        """
        avg_speed = self.average_speed_of_point("midpoint")
        return self.create_return_dictionary(uncategorized_data=avg_speed)

    @staticmethod
    def get_angle(base_point, outer_point):
        """
        Helper method for calculating angle between two points.

        Args:
            base_point(tuple[float, float]): First point
            outer_point(tuple[float, float]): Second point

        Returns:
            float: Angle given two points in degrees.
        """

        if outer_point[0] > base_point[0]:
            x = outer_point[0] - base_point[0]
        else:
            x = base_point[0] - outer_point[0]
        if outer_point[1] > base_point[1]:
            y = outer_point[1] - base_point[1]
        else:
            y = base_point[1] - outer_point[1]

        return math.degrees(math.atan(y / x))

    def avg_speed_of_points(self, keypoints=None, point_list=(DEFAULT_FOCUS_POINT_1, DEFAULT_FOCUS_POINT_2),
                            second=None):
        """
        Computes the average speed of one or more keypoints using recorded history.

        Args:
            point_list(list[str]): A list of keypoint names to measure.
            keypoints: Not Used.
            second: Not Used.

        Returns:
            dict[str, float]: Dictionary of average speed of each point requested.
        """
        speed_dict = {}
        if point_list is None:
            point_list = PART_MAP.values()
        for point in point_list:
            if point in PART_MAP.values():
                speed_dict[point] = self.average_speed_of_point(point)

        # Uncomment the following to have results logged to the console.
        # print("Average Speeds\n%s" % str(speed_dict))

        return self.create_return_dictionary(uncategorized_data=speed_dict)

    @staticmethod
    def absolute_speed(point_name, keypoints_a, keypoints_b):
        """
        Quickly calculates the absolute velocity between two sets of x,y co-ordinates with given timestamps.
        Args:
            point_name(str): Name of the point to measure.
            keypoints_a(dict): Dictionary of keypoints for point A.
            keypoints_b(dict): Dictionary of keypoints for point B.

        Returns:
            float: Velocity for movement between two points irrespective of direction.
        """

        abs_speed = 0.0
        if point_name in PART_MAP.values() or point_name == "midpoint":
            abs_speed = np.sqrt((abs(keypoints_a[point_name][0] - keypoints_b[point_name][0]) ** 2) +
                                (abs(keypoints_a[point_name][1] - keypoints_b[point_name][1]) ** 2)) / \
                        abs((keypoints_b["timestamp"] - keypoints_a["timestamp"]).microseconds)
        return abs_speed

    def average_speed_of_point(self, point_name):
        """
        Calculate the overage speed for a point based on history of keypoints.

        Args:
            point_name(str): Name of keypoint to measure.

        Returns:
            float: Average speed of a point over our history irrespetive of direction.
        """
        unreadable_entries = 0
        if point_name is not None and point_name == "midpoint":
            history = PoseMetrics.centroid_history
        else:
            history = PoseMetrics.history
        avg_speed = 0.0
        previous_keypoints = None
        if len(history) >= 2 and point_name is not None and (point_name in PART_MAP.values() or
                                                             point_name == "midpoint"):
            for keypoints in history:
                if previous_keypoints is not None:
                    # Wrap the call in a try, that way if a keypoint is "None" we dont crash and can count the number
                    # of spoiled entries and account for it in our averages.
                    try:
                        avg_speed += PoseMetrics.absolute_speed(point_name, keypoints, previous_keypoints)
                    except TypeError:
                        unreadable_entries += 1
                previous_keypoints = keypoints
            if unreadable_entries >= len(history) - 2:
                return 0
            avg_speed /= (len(history) - unreadable_entries)
        return avg_speed

    def positional_demo(self, keypoints, first=None, second=None):
        """
        Measures horizontal angle between two points and logs when the angle passes between a threshold angle.
        Logs results to console as True/False based on user interaction.

        Args:
            keypoints(dict): Parsed posenet dictionary of key-points.
            first: Not Used.
            second: Not Used.

        """
        if keypoints[self.POSITION_BASE]["score"] > MINIMUM_CONFIDENCE and \
                keypoints[self.POSITION_OUTER]["score"] > MINIMUM_CONFIDENCE:

            angle_horizontal = PoseMetrics.get_angle(keypoints[self.POSITION_BASE]["position"],
                                                     keypoints[self.POSITION_OUTER]["position"])
            current_angle = True if angle_horizontal > self.ANGLE_THRESHOLD else False
            if self.previous_angle is None:
                self.previous_angle = not current_angle
            if self.previous_angle != current_angle:
                print(" Over %s degrees?: %s | Confidence = %s:%s | Angle = %s",
                              self.ANGLE_THRESHOLD, current_angle, keypoints[self.POSITION_BASE]["score"],
                              keypoints[self.POSITION_OUTER]["score"], angle_horizontal)
            self.previous_angle = current_angle
        return None

    def simulation_pose_demo(self, keypoints, first=None, second=None):
        """
        Midpoint metric for simulation demo. Monitors right wrist in relation to middle point between nose and knees.
        Logs locations of key-points to console and forwards message to simulator.

        Args:
            keypoints(dict): A dictionary of parsed posenet key-points.
            first: Not Used.
            second: Not Used.

        """
        ret_dict = None
        # Check the confidence in all points required is above our threshold.
        if keypoints["nose"]["score"] > MINIMUM_CONFIDENCE and \
                keypoints["rightKnee"]["score"] > MINIMUM_CONFIDENCE and \
                keypoints["leftKnee"]["score"] > MINIMUM_CONFIDENCE and \
                keypoints["rightWrist"]["score"] > MINIMUM_CONFIDENCE:
            midpoint_y = (((keypoints["leftKnee"]["position"][1] + keypoints["rightKnee"]["position"][1]) / 2) +
                          keypoints["nose"]["position"][1]) / 2
            # Y axis is inverted, assign bool accordingly, Lower is larger, Higher is smaller
            above = False if keypoints["rightWrist"]["position"][1] > midpoint_y else True
            print(
                "High = %s, midpoint = %s, wrist_y = %s" % (above, midpoint_y, keypoints["rightWrist"]["position"][1]))
            if self.high is None:
                self.high = not above
            if self.high != above:
                print("Switch hover mode")
                print("High = %s, midpoint = %s, wrist_y = %s" % (
                    above, midpoint_y, keypoints["rightWrist"]["position"][1]))
                # Statically defined heights for drone locations for demo purposes.
                if above:
                    ret_dict = self.create_return_dictionary(x=0, y=0, z=3)
                else:
                    ret_dict = self.create_return_dictionary(x=0, y=0, z=1)
            self.high = above
        else:
            # Log keypoint data if confidence did not meet threshold.
            print("nose = %s, %s, knee1 = %s, %s, knee2 = %s, %s, wrist = %s, %s" % (keypoints["nose"]["score"],
                                                                                             keypoints["nose"][
                                                                                                 "position"],
                                                                                             keypoints["rightKnee"][
                                                                                                 "score"],
                                                                                             keypoints["rightKnee"][
                                                                                                 "position"],
                                                                                             keypoints["leftKnee"][
                                                                                                 "score"],
                                                                                             keypoints["leftKnee"][
                                                                                                 "position"],
                                                                                             keypoints["rightWrist"][
                                                                                                 "score"],
                                                                                             keypoints["rightWrist"][
                                                                                                 "position"]))
        return ret_dict

    def create_return_dictionary(self, x=default_x, y=default_y, z=default_z,
                                 rotation_x=default_rotation_x, rotation_y=default_rotation_y,
                                 rotation_z=default_rotation_z, rotation_w=default_rotation_w,
                                 velocity_x=default_velocity_x, velocity_y=default_velocity_y,
                                 velocity_z=default_velocity_z,
                                 velocity_angular_x=default_velocity_angular_x,
                                 velocity_angular_y=default_velocity_angular_y,
                                 velocity_angular_z=default_velocity_angular_z,
                                 acceleration_linear_x=default_acceleration_linear_x,
                                 acceleration_linear_y=default_acceleration_linear_y,
                                 acceleration_linear_z=default_acceleration_linear_z,
                                 acceleration_angular_x=default_acceleration_angular_x,
                                 acceleration_angular_y=default_acceleration_angular_y,
                                 acceleration_angular_z=default_acceleration_angular_z,
                                 proximity_value=None, uncategorized_data=None):
        """
        Creates a generically formatted dictionary based on any given values, filling unspecified parameters with
        predefined default values. This is used to create return variables for metrics so that calling metric functions
        is greatly simplified and more extensible.

        Args:
            x: x Location Co-ordinates.
            y: y Location Co-ordinates.
            z: z Location Co-ordinates.
            rotation_x: x rotation value.
            rotation_y: y rotation value.
            rotation_z: z rotation value.
            rotation_w: w rotation value.
            velocity_x: x linear velocity.
            velocity_y: y linear velocity.
            velocity_z: z linear velocity.
            velocity_angular_x: x angular velocity.
            velocity_angular_y: y angular velocity.
            velocity_angular_z: z angular velocity.
            acceleration_linear_x: x linear acceleration.
            acceleration_linear_y: y linear acceleration.
            acceleration_linear_z: z linear acceleration.
            acceleration_angular_x: x angular acceleration.
            acceleration_angular_y: y angular acceleration.
            acceleration_angular_z: z angular acceleration.
            proximity_value: Value between 0-1 corresponding to drones proximity to a left or right keypoint.
            uncategorized_data: Data not directly related to Drone parameters, eg. Average undirected speed of point(s).

        Returns:
            dict: The dictionary of all these values, populated with defaults for unspecified values.
        """
        dict_of_points = {
            "x": x,
            "y": y,
            "z": z,
            "rotation_x": rotation_x,
            "rotation_y": rotation_y,
            "rotation_z": rotation_z,
            "rotation_w": rotation_w,
            "velocity_x": velocity_x,
            "velocity_y": velocity_y,
            "velocity_z": velocity_z,
            "velocity_angular_x": velocity_angular_x,
            "velocity_angular_y": velocity_angular_y,
            "velocity_angular_z": velocity_angular_z,
            "acceleration_linear_x": acceleration_linear_x,
            "acceleration_linear_y": acceleration_linear_y,
            "acceleration_linear_z": acceleration_linear_z,
            "acceleration_angular_x": acceleration_angular_x,
            "acceleration_angular_y": acceleration_angular_y,
            "acceleration_angular_z": acceleration_angular_z,
            "proximity": proximity_value,
            "uncategorized_data": uncategorized_data
        }
        return dict_of_points

    # Helper dictionary for selecting functions for metrics.
    metric_list = {
        "positional_demo": positional_demo,
        "demo_metric": simulation_pose_demo,
        "offset_midpoints": midpoint,
        "centroid": centroid_movement_speed,
        "centroid_coords": centroid,
        "average_speed_of_points": avg_speed_of_points
    }

    def execute_metric(self, metric_name, keypoint_dict, first_list=None, second_list=None):
        """
        Executes a metric given its name. Always calls the metric function from the metric list with 3 arguments.

        Args:
            metric_name(str): Name of the metric defined in the dictionary.
            keypoint_dict(dict): Dictionary of current keypoints to be used.
            first_list(list): Optional list required by some metrics.
            second_list(list): Optional list required by some metrics.

        Returns:
            The result of the metric called.
        """
        try:
            for key in PART_MAP.values():
                if key not in keypoint_dict.keys():
                    return None
                if key != "timestamp" and (keypoint_dict[key] is None or keypoint_dict[key]["score"] is None or
                                           keypoint_dict[key]["score"] < MINIMUM_CONFIDENCE):
                    return None
            # Call the appropriate function from the metric_list dictionary with the name as the key.
            results = self.metric_list[metric_name](self, keypoint_dict, first_list, second_list)
        except KeyError:
            return None
        return results

    def get_histories(self):
        return self.history, self.centroid_history

    def clear_history(self):
        self.history.clear()
        self.centroid_history.clear()

    def load_history(self, username):
        with open(username + ".json", "r") as user_file:
            data = json.loads(user_file.read())
            try:
                self.history = data["history"]
                self.centroid_history = data["centroid_history"]
            except KeyError:
                pass

    def save_history(self, username):
        with open(username + ".json", "w") as user_file:
            data = {"history": self.history,
                    "centroid_history": self.centroid_history}
            user_file.write(json.dumps(data))


if __name__ == '__main__':
    # Startup for node.
    # TODO - These two lines are how to create the pose parser object and start the server.
    node = PoseParserNode.instance()
    node.listener()
