Position(
    self.wand_pos.x + round(math.cos(math.radians(self.wand_pos.yaw)),4) * self.length_from_wand,
    self.wand_pos.y + round(math.sin(math.radians(self.wand_pos.yaw)),4) * self.length_from_wand,
    ((self.wand_pos.z + round(
        math.sin(
            math.radians(self.wand_pos.pitch)), 4)
      * self.length_from_wand) if
     ((self.wand_pos.z + round(
         math.sin(
             math.radians(self.wand_pos.pitch)), 4)
       * self.length_from_wand) > 0) else 0)))

# proportion = self.circle_resolution/fast
#
# # if proportion >= 0 and proportion < .5:
# #     self.circle_height += .01
# #     self.circle_radius += .01
# #     # if self.circle_height >= self.circle_height_max:
# #     #     self.circle_height = self.circle_height_max
# #     #
# #     # if self.circle_radius >= self.circle_radius_max:
# #     #     self.circle_radius = self.circle_radius_max
# #
# # elif proportion >= .5 and proportion <= 1:
# #     self.circle_height -= .01
# #     self.circle_radius -= .01
# #     # if self.circle_height <= self.circle_height_min:
# #     #     self.circle_height = self.circle_height_min
# #     #
# #     # if self.circle_radius <= self.circle_radius_min:
# #     #     self.circle_radius = self.circle_radius_min
#
# logger.info('proportion {}'.format(proportion))
# logger.info('circle radius {}'.format(self.circle_radius))
# logger.info('circle_height {}'.format(self.circle_height))


# if point xx yy and zz are pointing at the drone, it slows down.
# if ((self.valid_cf_pos.x- leeway) <= self.end_of_wand.x < (self.valid_cf_pos.x + leeway)):
#     # if ((self.current_goal_pos.y - leeway) <= self.end_of_wand.y < (self.current_goal_pos.y + leeway)):
#         # if ((self.current_goal_pos.z - leeway) <= self.end_of_wand.z < (self.current_goal_pos.z + leeway)):
#     self.circle_resolution = slow
# else:
#     self.circle_resolution = fast