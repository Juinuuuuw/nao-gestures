"""Position telemetry must not inherit the slow ALMemory position mirror."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock,patch


class PositionSamplingTests(unittest.TestCase):
    def load(self):
        spec=importlib.util.spec_from_file_location('position_worker',Path(__file__).resolve().parents[1]/'app/robot_runner.py')
        worker=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'qi':types.SimpleNamespace()}):spec.loader.exec_module(worker)
        return worker

    def devices(self):
        # Cached device positions deliberately disagree with the motion service.
        return {'measured':[-99.],'commanded':[-88.],'hardness':[.4],
                'current_a':[.1],'temperature_c':[35.],'temperature_status':[0.]}

    def test_positions_are_fresh_motion_reads_metadata_is_cached_and_cannot_overwrite(self):
        worker=self.load();motion=Mock();memory=Mock()
        motion.getAngles.side_effect=[[.1],[.2],[.3],[.4],[.5],[.6]]
        with patch.object(worker,'read_arm_devices',return_value=self.devices()) as read_devices:
            sampler=worker.PositionSampler(motion,memory,['joint'],self.devices())
            records=[sampler.read(at) for at in (0.,.1,.41)]
        self.assertEqual([row['measured'] for row in records],[[.1],[.3],[.5]])
        self.assertEqual([row['commanded'] for row in records],[[.2],[.4],[.6]])
        self.assertEqual(read_devices.call_count,2)
        self.assertEqual(motion.getAngles.call_count,6)
        self.assertEqual([row['device_sample_elapsed_s'] for row in records],[0.,0.,.41])
        self.assertTrue(all(row['position_source']=='ALMotion.getAngles' for row in records))
        self.assertTrue(all(row['hardness']==[.4] for row in records))

    def test_optional_metadata_failure_preserves_position_sampling_and_reports_error(self):
        worker=self.load();motion=Mock();motion.getAngles.return_value=[.2]
        sampler=worker.PositionSampler(motion,Mock(),['joint'],self.devices())
        with patch.object(worker,'read_arm_devices',side_effect=RuntimeError('metadata offline')):
            row=sampler.read(0.)
        self.assertEqual(row['measured'],[.2]);self.assertEqual(row['commanded'],[.2])
        self.assertIn('metadata offline',row['device_read_error'])

    def test_constant_stiffness_aborts_if_required_metadata_becomes_unavailable(self):
        worker=self.load();motion=Mock();motion.getAngles.return_value=[.2]
        sampler=worker.PositionSampler(motion,Mock(),['joint'],self.devices(),strict_devices=True)
        with patch.object(worker,'read_arm_devices',side_effect=RuntimeError('metadata offline')):
            with self.assertRaisesRegex(RuntimeError,'metadata offline'):sampler.read(0.)

    def test_thermal_alert_is_not_hidden_by_position_reads(self):
        worker=self.load();motion=Mock();motion.getAngles.return_value=[.2]
        devices=self.devices();devices['temperature_status']=[1.]
        sampler=worker.PositionSampler(motion,Mock(),['joint'],self.devices(),strict_devices=True)
        with patch.object(worker,'read_arm_devices',return_value=devices):
            with self.assertRaisesRegex(RuntimeError,'termico'):sampler.read(0.)

    def test_invalid_motion_positions_are_rejected(self):
        worker=self.load();motion=Mock();motion.getAngles.return_value=[float('nan')]
        sampler=worker.PositionSampler(motion,Mock(),['joint'])
        with self.assertRaisesRegex(RuntimeError,'ALMotion'):sampler.read(0.)


if __name__=='__main__':unittest.main()
