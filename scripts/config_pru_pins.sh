#! /bin/bash
#---------------------------------------------------------
# Configures the PRU1 pins on the BeagleBone for FlockLab2
#
# for rev1.1:
# - Target_LED1 = P8.45
# - Target_LED2 = P8.46
# - Target_LED3 = P8.43
# - Target_INT1 = P8.44
# - Target_INT2 = P8.41
# - Target_SIG1 = P8.42
# - Target_SIG2 = P8.39
#
# for prototype rev1.0:
# - Target_LED1 = P8.42
# - Target_LED2 = P8.44
# - Target_LED3 = P8.46
# - Target_INT1 = P8.43
# - Target_INT2 = P8.45
# - Target_SIG1 = P8.28
# - Target_SIG2 = P8.40
#
# 2019, rdaforno
#---------------------------------------------------------




# TRACING PINS

# Target_LED1
config-pin -a P845 pruin
config-pin -q P845
# Target_LED2
config-pin -a P846 pruin
config-pin -q P846
# Target_LED3
config-pin -a P843 pruin
config-pin -q P843
# Target_INT1
config-pin -a P844 pruin
config-pin -q P844
# Target_INT2
config-pin -a P841 pruin
config-pin -q P841
# PRU_SYNC
#config-pin -a P829 pruin
#config-pin -q P829

# ACTUATION PINS

# Target_SIG1
config-pin -a P842 pruout
config-pin -q P842
# Target_SIG2
config-pin -a P839 pruout
config-pin -q P839
# Flock_nRST
#config-pin -a P839 pruout
#config-pin -q P839

# DEBUG PINS
config-pin -a P828 pruout
config-pin -q P828
config-pin -a P840 pruout
config-pin -q P840
