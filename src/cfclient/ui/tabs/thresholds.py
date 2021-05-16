import math

# def __init__():
#     loops_spent_with_condition_met = 0
#     isUnlocked = False
#     # xcomp as
#     # lh_pos.x

def wide_hands(lh_pos, cf_pos, rh_pos):
    is_wide = False
    if lh_pos.distance_to(cf_pos) > .4 and rh_pos.distance_to(cf_pos) > .4:
        is_wide = True

    return is_wide

def check_condition(lh_pos, cf_pos , rh_pos, loops_spent_with_condition_met, isUnlocked):
    if wide_hands(lh_pos, cf_pos, rh_pos) and not isUnlocked:
        loops_spent_with_condition_met = loops_spent_with_condition_met + 1
        print('loops_spent_with_condition_met', loops_spent_with_condition_met)

        if(loops_spent_with_condition_met > 1000 ):
            print('unlocking')
            isUnlocked = True
    else:
        print('condition not yet met')


