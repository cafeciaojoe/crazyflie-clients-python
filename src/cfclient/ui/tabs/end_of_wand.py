import math
import numpy as np

# One way to find the point you are looking for is to start with a vector to the point, in the CF reference frame.
## v = [0, 0, -d]
## and then rotate it to the global reference frame using the rotation matrix (R) that represents the CF rotation and finally add the position of the CF (P).
## R dot v + P
## In numpy this would be something like

def _rotation_matrix(roll, pitch, yaw):
    # http://planning.cs.uiuc.edu/node102.html
    # Pitch reversed compared to page above
    cg = math.cos(roll)
    cb = math.cos(-pitch)
    ca = math.cos(yaw)
    sg = math.sin(roll)
    sb = math.sin(-pitch)
    sa = math.sin(yaw)

    r = [
        [ca * cb, ca * sb * sg - sa * cg, ca * sb * cg + sa * sg],
        [sa * cb, sa * sb * sg + ca * cg, sa * sb * cg - ca * sg],
        [-sb, cb * sg, cb * cg],
    ]

    return np.array(r)

def calculate_offset(d, cf_x, cf_y, cf_z,cf_roll, cf_pitch, cf_yaw):
    roll = math.radians(cf_roll)
    pitch = math.radians(cf_pitch)
    yaw = math.radians(cf_yaw)

    v = np.array([0.0,0.0,-d])
    P = np.array([cf_x, cf_y, cf_z])
    R = _rotation_matrix(roll, pitch, yaw)
    offset = np.dot(R, v) + P
    return offset
