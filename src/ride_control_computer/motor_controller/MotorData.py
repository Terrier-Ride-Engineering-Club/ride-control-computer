from statistics import fmean
speeds = []

def addSpeed(value):
    speeds.append(value)

def getSpeeds():
    return speeds

def getAverageSpeed():
    return fmean(speeds)