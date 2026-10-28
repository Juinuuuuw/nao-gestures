import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('test_virtual_hand_module',Path(__file__).resolve().parents[1]/'webots/controllers/gesture_player/virtual_hand.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class Motor:
    def __init__(self,name):self.name=name;self.value=.25;self.torque=None;self.step=None
    def getName(self):return self.name
    def getMinPosition(self):return 0.
    def getMaxPosition(self):return 1.
    def getMaxVelocity(self):return 5.
    def getMaxTorque(self):return 1.
    def setAvailableTorque(self,value):self.torque=value
    def setVelocity(self,value):self.velocity=value
    def setPosition(self,value):self.value=value
    def getPositionSensor(self):return self
    def enable(self,step):self.step=step
    def getValue(self):return self.value

class Robot:
    def __init__(self):self.motors=[Motor('LPhalanx1'),Motor('LPhalanx2'),Motor('RPhalanx1')]
    def getNumberOfDevices(self):return len(self.motors)
    def getDeviceByIndex(self,index):return self.motors[index]

class VirtualHandTests(unittest.TestCase):
    def test_open_fraction_cancels_the_models_curled_rest_rotation(self):
        robot=Robot();hand=module.VirtualHand(robot,'L')
        hand.setPosition(1.);self.assertEqual([m.value for m in robot.motors[:2]],[.96,.96])
        self.assertEqual(hand.getPositionSensor().getValue(),1.)
        hand.setPosition(0.);self.assertEqual([m.value for m in robot.motors[:2]],[0.,0.])
        self.assertEqual(hand.getPositionSensor().getValue(),0.)
        self.assertEqual(robot.motors[-1].value,.25)
    def test_sensors_velocity_and_simulated_torque_are_coupled(self):
        robot=Robot();hand=module.VirtualHand(robot,'L');hand.getPositionSensor().enable(12)
        hand.setPosition(.42);hand.setVelocity(1.)
        self.assertAlmostEqual(hand.getPositionSensor().getValue(),.42)
        self.assertTrue(all(m.step==12 and m.torque==.08 and abs(m.velocity-.96)<1e-12 for m in robot.motors[:2]))

if __name__=='__main__':unittest.main()
