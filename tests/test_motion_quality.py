import json
import math
import unittest

from app.motion_quality import analyze_telemetry


class MotionQualityTests(unittest.TestCase):
    def rows(self,commands,measured,times=None):
        if times is None:times=[k*.1 for k in range(len(commands))]
        return [{'elapsed_s':t,'commanded':[math.radians(c)],'measured':[math.radians(q)]}
                for t,c,q in zip(times,commands,measured)]

    def test_smooth_tracking_has_no_unplanned_pause(self):
        rows=self.rows(range(12),[x-.1 for x in range(12)])
        result=analyze_telemetry(rows,['Shoulder'])
        self.assertEqual(result['unplanned_pause_count'],0)
        self.assertAlmostEqual(result['tracking_rms_deg'],.1)
        self.assertAlmostEqual(result['joints']['Shoulder']['measured_range_deg'],11.)
        json.dumps(result,allow_nan=False)

    def test_planned_stop_is_not_reported_as_a_stuck_sensor(self):
        commands=[0.,1.,2.,3.,3.,3.,3.,3.,3.,4.,5.]
        result=analyze_telemetry(self.rows(commands,commands))
        self.assertEqual(result['unplanned_pause_count'],0)

    def test_stuck_sensor_during_commanded_motion_is_reported(self):
        rows=self.rows([0.,.5,1.,1.5,2.,2.5],[0.,.03,.06,.02,.04,.01])
        result=analyze_telemetry(rows,['Shoulder'])
        joint=result['joints']['Shoulder']
        self.assertEqual(joint['pause_count'],1)
        pause=joint['pauses'][0]
        self.assertAlmostEqual(pause['duration_s'],.5)
        self.assertAlmostEqual(pause['command_travel_deg'],2.5)
        self.assertLess(pause['sensor_range_deg'],.15)
        self.assertGreater(joint['tracking_rms_deg'],1.)

    def test_speech_window_excludes_entry_and_return(self):
        rows=self.rows([0.,1.,2.,3.,4.,5.,6.,7.,8.,9.],
                       [0.,0.,0.,0.,4.,5.,6.,7.,7.,7.])
        all_motion=analyze_telemetry(rows)
        speech=analyze_telemetry(rows,speech_bounds=(.4,.7))
        self.assertGreater(all_motion['unplanned_pause_count'],0)
        self.assertEqual(speech['unplanned_pause_count'],0)
        self.assertEqual(speech['sample_count'],4)

    def test_dropped_samples_do_not_imply_a_pause(self):
        rows=self.rows([0.,1.,2.,3.],[0.,0.,0.,0.],[0.,.1,1.,1.1])
        result=analyze_telemetry(rows)
        self.assertEqual(result['unplanned_pause_count'],0)

    def test_short_or_tiny_command_changes_do_not_imply_a_pause(self):
        for commands,times in [([0.,1.],[0.,.1]),([0.,.1,.2,.3],[0.,.1,.2,.3])]:
            result=analyze_telemetry(self.rows(commands,[0.]*len(commands),times))
            self.assertEqual(result['unplanned_pause_count'],0)

    def test_nonfinite_values_and_nonmonotonic_times_are_rejected(self):
        for rows in [self.rows([0.,1.],[0.,float('nan')]),
                     self.rows([0.,1.],[0.,1.],[.1,.1])]:
            with self.assertRaises(ValueError):analyze_telemetry(rows)


if __name__=='__main__':
    unittest.main()
