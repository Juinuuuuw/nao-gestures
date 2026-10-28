"""Read-only physical NAO diagnostics using the installed official qicli client.

Only the fixed list of read methods below is called. No stiffness, posture,
audio, autonomous-life or motor state is changed.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess

def main():
    root=Path(__file__).resolve().parents[1]
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='192.168.17.62')
    p.add_argument('--port',type=int,default=9561)
    p.add_argument('--out',type=Path,default=root/'physical_robot_status.json')
    p.add_argument('--qicli',type=Path,default=Path(os.environ['LOCALAPPDATA'])/'Programs/Aldebaran/choregraphe-suite-2.8.7.4-win64-vs2015/bin/qicli.exe')
    args=p.parse_args()
    if not args.qicli.is_file():raise FileNotFoundError('Official qicli not found: '+str(args.qicli))
    def read(method,*parameters):
        command=[str(args.qicli),'--qi-url','tcp://%s:%d'%(args.host,args.port),'--qi-log-level','2','call','--json',method]
        command.extend(json.dumps(x) for x in parameters)
        result=subprocess.run(command,capture_output=True,text=True,timeout=10)
        if result.returncode:raise RuntimeError(method+': '+(result.stderr or result.stdout).strip())
        return json.loads(result.stdout.strip())
    report={'host':args.host,'port':args.port,'checked_at_utc':datetime.now(timezone.utc).isoformat(),'read_only':True,'motor_commands_sent':False}
    methods={
        'naoqi_version':('ALSystem.systemVersion',),
        'posture':('ALRobotPosture.getPosture',),
        'battery_percent':('ALBattery.getBatteryCharge',),
        'robot_config':('ALMotion.getRobotConfig',),
        'left_arm_joint_names':('ALMotion.getBodyNames','LArm'),
        'right_arm_joint_names':('ALMotion.getBodyNames','RArm'),
        'left_arm_limits':('ALMotion.getLimits','LArm'),
        'right_arm_limits':('ALMotion.getLimits','RArm'),
        'head_limits':('ALMotion.getLimits','Head'),
        'left_arm_sensor_angles_rad':('ALMotion.getAngles','LArm',True),
        'right_arm_sensor_angles_rad':('ALMotion.getAngles','RArm',True),
        'autonomous_life_state':('ALAutonomousLife.getState',)
    }
    failures={}
    for key,call in methods.items():
        try:report[key]=read(*call)
        except Exception as error:failures[key]=str(error)
    report['read_errors']=failures
    report['naoqi_connection_confirmed']='naoqi_version' in report
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    config_path=root/'robot_connection.json'
    config=json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    config.update({'host':args.host,'naoqi_port':args.port,'physical_motor_control_enabled':False,'naoqi_connection_confirmed':report['naoqi_connection_confirmed']})
    config.setdefault('last_read_only_check',{}).update({'checked_at_utc':report['checked_at_utc'],'naoqi_port_%d_responded'%args.port:report['naoqi_connection_confirmed'],'firmware_version_confirmed':'naoqi_version' in report,'motor_commands_sent':False})
    if 'naoqi_version' in report:config['naoqi_version']=report['naoqi_version']
    config_path.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:report.get(key) for key in ('host','port','naoqi_version','posture','battery_percent','autonomous_life_state','read_errors','motor_commands_sent')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
