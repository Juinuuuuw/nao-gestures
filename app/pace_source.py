"""Recover raw IK targets for existing generations without changing their preview."""
import json
import math
import os
from pathlib import Path
import tempfile

from nao_gestures.inputs import load_npz
from nao_gestures.retarget import fit


def _fingerprint(paths):
    return {path.name:{'size':path.stat().st_size,'mtime_ns':path.stat().st_mtime_ns}
            for path in paths}


def _valid_raw(raw,trajectory):
    try:
        count=len(trajectory['angles_rad']);joints=len(trajectory['joint_names'])
        return (len(raw)==count and count>=3 and joints>0
                and all(len(row)==joints and all(math.isfinite(float(v)) for v in row) for row in raw))
    except (KeyError,TypeError,ValueError,OverflowError):
        return False


def load_execution_trajectory(directory:Path):
    """Return the original trajectory plus raw IK targets, cached separately.

    Older generations without EMAGE/rest inputs explicitly retain their original
    trajectory with no added raw-target field. The physical planner can identify
    that fallback. Corrupt or stale caches are ignored and regenerated.
    """
    directory=Path(directory)
    original_path=directory/'trajectory.json'
    trajectory=json.loads(original_path.read_text(encoding='utf-8-sig'))
    if 'source_joint_targets_rad' in trajectory:
        return trajectory
    motion=directory/'emage_motion.npz';rest=directory/'rest_joints.npy'
    if not motion.is_file() or not rest.is_file():
        return trajectory
    sources=(original_path,motion,rest)
    fingerprint=_fingerprint(sources)
    cache_path=directory/'execution_source.json'
    try:
        cache=json.loads(cache_path.read_text(encoding='utf-8'))
        cached=cache['trajectory']
        if (cache.get('schema')=='nao-execution-source-v1'
                and cache['fingerprint']==fingerprint
                and _valid_raw(cached['source_joint_targets_rad'],trajectory)):
            # Only the recovered targets are reused; all other fields remain
            # authoritative in the original trajectory.
            result=dict(trajectory)
            result['source_joint_targets_rad']=cached['source_joint_targets_rad']
            result['source_joint_targets_representation']='unfiltered IK joint positions; not spline control coefficients'
            return result
    except (OSError,ValueError,KeyError,TypeError):
        pass
    arms,fps,_=load_npz(motion,rest)
    raw=fit(arms,fps,include_raw=True)[4].tolist()
    if not _valid_raw(raw,trajectory):
        raise ValueError('Os alvos IK recuperados não correspondem à trajetória original.')
    # Avoid saving an IK result under an input fingerprint that changed mid-fit.
    if _fingerprint(sources)!=fingerprint:
        raise ValueError('Os arquivos da geração mudaram durante a preparação. Tente novamente.')
    result=dict(trajectory)
    result['source_joint_targets_rad']=raw
    result['source_joint_targets_representation']='unfiltered IK joint positions; not spline control coefficients'
    payload={'schema':'nao-execution-source-v1','fingerprint':fingerprint,'trajectory':result}
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=directory,
                                         prefix='.execution-source-',suffix='.tmp',delete=False) as output:
            temporary=Path(output.name)
            json.dump(payload,output,ensure_ascii=False,allow_nan=False)
        os.replace(temporary,cache_path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return result
