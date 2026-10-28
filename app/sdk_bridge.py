"""Run the already installed Choregraphe Python SDK without global env changes."""
import os
from pathlib import Path
import subprocess

def launch_bridge(arguments,**kwargs):
    suite=Path(os.environ['LOCALAPPDATA'])/'Programs/Aldebaran/choregraphe-suite-2.8.7.4-win64-vs2015'
    env=os.environ.copy()
    env['PYTHONHOME']=str(suite/'lib/python2.7')
    env['PYTHONPATH']=os.pathsep.join([str(suite/'lib/python2.7/Lib/site-packages'),str(suite/'lib')])
    env['PATH']=os.pathsep.join([str(suite/'bin'),str(suite/'lib/python2.7/Lib/site-packages/qi/win'),env.get('PATH','')])
    runner=Path(__file__).with_name('robot_runner.py')
    return subprocess.Popen([str(suite/'bin/python.exe'),'-u',str(runner),*map(str,arguments)],env=env,**kwargs)
