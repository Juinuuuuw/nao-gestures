"""NAOqi 0..1 openness mapped to the installed Webots phalanx joints.

The model has no LHand/RHand motor. All finger links are coupled here for a
visual approximation, not a calibrated reconstruction of the physical tendon.
"""
class HandSensor:
    def __init__(self,hand):self.hand=hand
    def enable(self,step):
        for motor in self.hand.motors:motor.getPositionSensor().enable(step)
    def getValue(self):
        values=[]
        for motor,lo,hi in self.hand.links:
            value=motor.getPositionSensor().getValue()
            values.append(max(0.,min(1.,(value-lo)/(hi-lo))))
        return sum(values)/len(values)

class VirtualHand:
    def __init__(self,robot,side):
        self.name=side+'Hand';self.motors=[];self.links=[]
        for index in range(robot.getNumberOfDevices()):
            motor=robot.getDeviceByIndex(index)
            if motor.getName().startswith(side+'Phalanx') and hasattr(motor,'setPosition'):
                # This PROTO starts curled at -0.96 rad in its Solid rotation.
                # A positive motor angle of +0.96 straightens the finger.
                lo=max(0.,motor.getMinPosition());hi=min(.96,motor.getMaxPosition())
                if hi<=lo:raise ValueError('Invalid phalanx range')
                self.motors.append(motor);self.links.append((motor,lo,hi))
                if hasattr(motor,'setAvailableTorque'):motor.setAvailableTorque(min(.08,motor.getMaxTorque()))
        if not self.motors:raise ValueError('No fingers found for '+self.name)
        self.sensor=HandSensor(self)
    def getMinPosition(self):return 0.
    def getMaxPosition(self):return 1.
    def getMaxVelocity(self):return 1.2
    def setVelocity(self,value):
        for motor,lo,hi in self.links:motor.setVelocity(min(value*(hi-lo),motor.getMaxVelocity()))
    def setPosition(self,value):
        value=max(0.,min(1.,float(value)))
        for motor,lo,hi in self.links:motor.setPosition(lo+value*(hi-lo))
    def getPositionSensor(self):return self.sensor
