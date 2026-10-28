"""Existing generations can gain raw execution targets without replacing previews."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from app import pace_source


class PaceSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.trajectory={'angles_rad':[[0.]*8 for _ in range(3)],
                         'times_s':[0.,1/30,2/30],'joint_names':['joint_%d'%j for j in range(8)]}
        self.path=self.root/'trajectory.json'
        self.path.write_text(json.dumps(self.trajectory,indent=2),encoding='utf-8')
        self.original=self.path.read_bytes()
        self.motion=self.root/'emage_motion.npz';self.motion.write_bytes(b'motion fixture')
        (self.root/'rest_joints.npy').write_bytes(b'rest fixture')
        self.raw=np.arange(24,dtype=float).reshape(3,8)/100
        self.load=patch.object(pace_source,'load_npz',return_value=(np.zeros((3,2,3,3)),30.,'test'))
        self.fit_patch=patch.object(pace_source,'fit',return_value=(None,None,None,{},self.raw))
        self.loader=self.load.start();self.addCleanup(self.load.stop)
        self.fit=self.fit_patch.start();self.addCleanup(self.fit_patch.stop)

    def test_cache_is_reused_and_invalidated_by_source_timestamp(self):
        first=pace_source.load_execution_trajectory(self.root)
        second=pace_source.load_execution_trajectory(self.root)
        self.assertEqual(first,second)
        self.assertEqual(self.fit.call_count,1)
        self.assertEqual(self.loader.call_count,1)
        self.assertTrue(self.fit.call_args.kwargs['include_raw'])
        cache=json.loads((self.root/'execution_source.json').read_text(encoding='utf-8'))
        self.assertEqual(set(cache['fingerprint']),{'trajectory.json','emage_motion.npz','rest_joints.npy'})
        self.assertTrue(all(set(v)=={'size','mtime_ns'} for v in cache['fingerprint'].values()))
        stat=self.motion.stat()
        os.utime(self.motion,ns=(stat.st_atime_ns,stat.st_mtime_ns+1_000_000_000))
        pace_source.load_execution_trajectory(self.root)
        self.assertEqual(self.fit.call_count,2)
        self.assertEqual(self.path.read_bytes(),self.original)
        self.assertEqual(list(self.root.glob('.execution-source-*.tmp')),[])

    def test_cache_is_invalidated_by_original_trajectory_change(self):
        pace_source.load_execution_trajectory(self.root)
        self.trajectory['source']='new metadata'
        self.path.write_text(json.dumps(self.trajectory),encoding='utf-8')
        result=pace_source.load_execution_trajectory(self.root)
        self.assertEqual(self.fit.call_count,2)
        self.assertEqual(result['source'],'new metadata')

    def test_embedded_raw_targets_skip_recovery_and_cache(self):
        self.trajectory['source_joint_targets_rad']=self.raw.tolist()
        self.path.write_text(json.dumps(self.trajectory),encoding='utf-8')
        result=pace_source.load_execution_trajectory(self.root)
        self.assertEqual(result,self.trajectory)
        self.fit.assert_not_called();self.loader.assert_not_called()
        self.assertFalse((self.root/'execution_source.json').exists())

    def test_missing_inputs_returns_explicit_original_fallback(self):
        self.motion.unlink()
        result=pace_source.load_execution_trajectory(self.root)
        self.assertEqual(result,self.trajectory)
        self.assertNotIn('source_joint_targets_rad',result)
        self.fit.assert_not_called();self.loader.assert_not_called()
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_corrupt_or_invalid_cache_is_recomputed(self):
        cache=self.root/'execution_source.json'
        cache.write_text('{broken',encoding='utf-8')
        pace_source.load_execution_trajectory(self.root)
        payload=json.loads(cache.read_text(encoding='utf-8'))
        payload['trajectory']['source_joint_targets_rad']=[[0.]]
        cache.write_text(json.dumps(payload),encoding='utf-8')
        result=pace_source.load_execution_trajectory(self.root)
        self.assertEqual(result['source_joint_targets_rad'],self.raw.tolist())
        self.assertEqual(self.fit.call_count,2)
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_failed_atomic_replace_does_not_modify_original_and_cleans_temporary(self):
        with patch.object(pace_source.os,'replace',side_effect=OSError('Disk error')):
            with self.assertRaisesRegex(OSError,'Disk error'):
                pace_source.load_execution_trajectory(self.root)
        self.assertEqual(self.path.read_bytes(),self.original)
        self.assertEqual(list(self.root.glob('.execution-source-*.tmp')),[])
        self.assertFalse((self.root/'execution_source.json').exists())


if __name__=='__main__':unittest.main()
