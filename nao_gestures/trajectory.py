"""Uniform cubic B-spline with repeated end coefficients and a fixed clock.

First/last coefficient differences must be zero for a stationary entry/exit.
Velocity and acceleration are convex combinations of coefficient differences.
"""
import numpy as np

class UniformCubic:
    def __init__(self, coefficients, fps):
        self.q=np.asarray(coefficients,dtype=float)
        self.fps=float(fps)

    def __call__(self, time):
        z=np.clip(np.asarray(time)*self.fps,0,len(self.q)-1)
        i=np.floor(z).astype(int);u=z-i
        c=[self.q[np.clip(i+k,0,len(self.q)-1)] for k in (-1,0,1,2)]
        weights=[(1-u)**3,3*u**3-6*u**2+4,-3*u**3+3*u**2+3*u+1,u**3]
        return sum(a*w[...,None] for a,w in zip(c,weights))/6
