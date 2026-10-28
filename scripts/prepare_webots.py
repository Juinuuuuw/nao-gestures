"""Build a separate local Webots lab from the user's installed NAO V6 assets."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path);p.add_argument('--python',required=True,type=Path);args=p.parse_args()
    project=Path(__file__).resolve().parents[1]/'webots'
    proto=project/'protos';proto.mkdir(parents=True,exist_ok=True)
    records=[]
    for name in ('NaoV6.proto','NaoLeftWristH25Realistic.proto','NaoRightWristH25Realistic.proto','textures/chest_button.png','textures/ear.jpg'):
        source=args.source/name;target=proto/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
        records.append({'source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    body=proto/'NaoV6.proto';text=body.read_text(encoding='utf-8')
    # Webots motor ranges must include zero in the reference configuration.
    # Enforce the narrower physical elbow limit in our trajectory/controller.
    text=text.replace('#maxPosition -0.0349','maxPosition 0  # Physical max -0.0349 is enforced by gesture_player.')
    body.write_text(text,encoding='utf-8')
    controller=project/'controllers'/'gesture_player'
    (controller/'runtime.ini').write_text('[python]\nCOMMAND = '+args.python.resolve().as_posix()+'\nOPTIONS = -u\n',encoding='utf-8')
    project_file=project/'worlds/.gesture_lab.wbproj'
    lines=project_file.read_text(encoding='utf-8-sig').splitlines() if project_file.exists() else ['Webots Project File version R2025a']
    lines=[line for line in lines if not line.startswith('renderingDevicePerspectives:')]
    lines += ['renderingDevicePerspectives: NAO V6 - Gesture Lab:CameraTop;0;1;0;0','renderingDevicePerspectives: NAO V6 - Gesture Lab:CameraBottom;0;1;0;0']
    project_file.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (project/'assets_manifest.json').write_text(json.dumps({'source_assets':records,'modifications':['Explicit zero-inclusive simulator LElbowRoll range; physical elbow bounds enforced in controller.'],'license_note':'Model assets copied from the installed WebotsLoLaController project; upstream rights and attribution apply.'},indent=2),encoding='utf-8')
    print(project)

if __name__=='__main__':main()
