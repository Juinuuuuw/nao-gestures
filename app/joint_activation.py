"""Scoped activation of relaxed wrist/hand motors, compatible with SDK Python 2."""
class JointActivation(object):
    def __init__(self,motion,names,stiffness,expected,minimum=.6):
        self.motion=motion;self.names=names;self.original=list(stiffness)
        self.expected=list(expected);self.minimum=minimum;self.changed=False

    def __enter__(self):
        if min(self.original)>=self.minimum:return self
        current=self.motion.getAngles(self.names,True)
        if len(current)!=len(self.expected) or any(abs(a-b)>.08 for a,b in zip(current,self.expected)):
            raise RuntimeError('Punhos/maos mudaram de postura. Tente novamente.')
        self.motion.setAngles(self.names,current,.02)
        self.changed=True
        try:self.motion.stiffnessInterpolation(self.names,[max(self.minimum,x) for x in self.original],.4)
        except BaseException:
            self.motion.stiffnessInterpolation(self.names,self.original,.4)
            self.changed=False
            raise
        return self

    def __exit__(self,*args):
        if self.changed:
            self.changed=False
            self.motion.stiffnessInterpolation(self.names,self.original,.4)
        return False
