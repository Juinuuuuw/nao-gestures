import unittest
from unittest.mock import Mock
import numpy as np
from app.emotion import PROFILES,profile,expression_script
from app.robot_plan import build_plan,bezier_bounds,PACES
from app.plan_preview import sample_plan,speech_preview
from app.eye_expression import EyeExpression,EyeResources
from nao_gestures.kinematics import REST,NAMES

class EmotionTests(unittest.TestCase):
    def fixture(self,key):
        t=np.arange(181)/30;q=np.tile(REST,(len(t),1))
        q[:,0]+=.3*np.sin(t*2);q[:,4]+=.2*np.cos(t*2)
        source={'joint_names':NAMES,'times_s':t.tolist(),'angles_rad':q.tolist(),'interpolation':'uniform_cubic_control_points'}
        plan=build_plan(source,REST,head_targets=np.zeros((len(t),2)),current_head=[0,0],
                        direction={'events':[],'method':'test'},current_manual=[0,0,.42,.42],emotion=key)
        plan['initial_angles']=REST.tolist()+[0,0,0,0,.42,.42]
        return plan

    def test_six_emotions_plus_neutral_keep_physical_limits_and_clock(self):
        self.assertEqual(len(PROFILES),7)
        samples=[]
        for key in PROFILES:
            with self.subTest(emotion=key):
                plan=self.fixture(key);bounds=bezier_bounds(plan)
                self.assertEqual(plan['emotion'],key)
                self.assertEqual(plan['names'][-2:],['LHand','RHand'])
                self.assertAlmostEqual(plan['speech_duration_s'],6.)
                self.assertLessEqual(bounds['velocity_bound_rad_s'],PACES['natural']['velocity']+.001)
                self.assertLessEqual(bounds['acceleration_bound_rad_s2'],PACES['natural']['acceleration']+.001)
                self.assertLessEqual(bounds['hand_velocity_bound_fraction_s'],1.001)
                self.assertLessEqual(bounds['hand_acceleration_bound_fraction_s2'],3.001)
                preview=speech_preview(plan)
                self.assertEqual(preview['emotion'],key)
                samples.append(sample_plan(plan,np.array([plan['audio_start_s']+3.]))[0])
        self.assertEqual(len({tuple(np.round(row,4)) for row in samples}),7)

    def test_score_uses_real_word_times_and_never_alters_spoken_content(self):
        speech={'text':'Uma descoberta mudou tudo.','words':[dict(text=w,start_s=i*.6) for i,w in enumerate(['Uma','descoberta','mudou','tudo'])]}
        before=speech['text']
        for key in PROFILES:
            score=expression_script(speech,key)
            self.assertEqual(score['emotion_label'],PROFILES[key]['label'])
            np.testing.assert_allclose([x['at_s'] for x in score['cues']],[0.,1.2,1.8])
            self.assertIn('(',score['speech_and_gestures'])
            self.assertEqual(speech['text'],before)

    def test_invalid_emotion_rejected(self):
        for key in ['ecstatic','../../bad',None,{},True]:
            with self.assertRaises(ValueError):profile(key)

    def test_emotions_change_posture_hands_and_head_in_different_ways(self):
        samples={key:sample_plan(self.fixture(key),np.linspace(2.,4.,30)+self.fixture(key)['audio_start_s']) for key in ('joy','sadness','fear','anger','disgust')}
        # Broad qualitative requirements survive smoothing and actuator limits.
        self.assertGreater(samples['sadness'][:,0].mean(),samples['joy'][:,0].mean()+.12)
        self.assertGreater(np.abs(samples['fear'][:,3]).mean(),np.abs(samples['joy'][:,3]).mean()+.15)
        self.assertGreater(samples['joy'][:,-2:].mean(),samples['anger'][:,-2:].mean()+.10)
        self.assertGreater(samples['disgust'][:,8].mean(),.05)

    def test_timed_emotion_accents_change_the_planned_curve(self):
        from app.emotion import apply_emotion
        t=np.arange(241)/30;q=np.tile(REST,(len(t),1));head=np.zeros((len(t),2));hands=np.tile([0,0,.5,.5],(len(t),1))
        first=apply_emotion(q,head,hands,t,'anger',cue_times=[2.])
        second=apply_emotion(q,head,hands,t,'anger',cue_times=[5.])
        self.assertLess(first[0][60,0],second[0][60,0]-.05)
        self.assertGreater(first[1][60,1],second[1][60,1]+.03)

class EyeExpressionTests(unittest.TestCase):
    def fixture(self):
        leds=Mock();leds.listGroup.return_value=['Face/Led/Red/Left/0Deg/Actuator/Value','Face/Led/Green/Right/0Deg/Actuator/Value']
        leds.getIntensity.side_effect=[.2,.7]
        return leds,EyeExpression(leds,0xFFD060)

    def test_restore_exact_channels_even_after_expression(self):
        leds,scope=self.fixture();scope.prepare();leds.fadeRGB.assert_not_called()
        scope.start();scope.restore()
        leds.fadeRGB.assert_called_once_with('FaceLeds',0xFFD060,.12)
        self.assertEqual([call.args[1] for call in leds.setIntensity.call_args_list],[.2,.7])

    def test_failed_start_restores_channels(self):
        leds,scope=self.fixture();leds.fadeRGB.side_effect=RuntimeError('LED unavailable')
        with self.assertRaises(RuntimeError):scope.start()
        self.assertEqual(leds.setIntensity.call_count,2)

    def test_invalid_group_or_snapshot_never_changes_leds(self):
        leds,scope=self.fixture();leds.listGroup.return_value=['ChestBoard/Led/Red/Actuator/Value']
        with self.assertRaises(RuntimeError):scope.start()
        leds.fadeRGB.assert_not_called()

    def test_restore_attempts_remaining_channels_after_error(self):
        leds,scope=self.fixture();scope.start();leds.setIntensity.side_effect=[RuntimeError('failed'),None]
        with self.assertRaises(RuntimeError):scope.restore()
        self.assertEqual(leds.setIntensity.call_count,2)

    def test_color_is_held_for_multiple_seconds_without_resnapshot(self):
        leds,scope=self.fixture();scope.start(now=0.)
        self.assertFalse(scope.maintain(now=.2))
        for now in [.5,1.,1.5,2.,3.]:self.assertTrue(scope.maintain(now=now))
        self.assertEqual(scope.refresh_count,5)
        self.assertEqual(leds.getIntensity.call_count,2)
        self.assertEqual(leds.fadeRGB.call_count,6)
        self.assertEqual(leds.fadeRGB.call_args.args,('FaceLeds',0xFFD060,.05))
        scope.restore();self.assertFalse(scope.maintain(now=4.))
        self.assertEqual(leds.fadeRGB.call_count,6)

    def test_hold_failure_still_allows_original_color_restoration(self):
        leds,scope=self.fixture();scope.start(now=0.)
        leds.fadeRGB.side_effect=RuntimeError('Refresh failed')
        with self.assertRaises(RuntimeError):scope.maintain(now=1.)
        self.assertFalse(scope.maintain(now=2.))
        scope.restore();self.assertEqual(leds.setIntensity.call_count,2)

class EyeResourcesTests(unittest.TestCase):
    def test_only_eye_resources_are_owned_and_release_is_idempotent(self):
        session=Mock();manager=Mock();session.registerService.return_value=42
        scope=EyeResources(session,manager);scope.acquire();scope.release();scope.release()
        manager.acquireResourcesTree.assert_called_once_with(['Left eye leds','Right eye leds'],scope.name,'onConflict',0)
        manager.releaseResources.assert_called_once_with(['Left eye leds','Right eye leds'],scope.name)
        session.unregisterService.assert_called_once_with(42)

    def test_failed_acquire_unregisters_and_does_not_leave_partial_claim(self):
        session=Mock();manager=Mock();session.registerService.return_value=42
        manager.acquireResourcesTree.side_effect=RuntimeError('busy')
        scope=EyeResources(session,manager)
        with self.assertRaises(RuntimeError):scope.acquire()
        manager.releaseResources.assert_called_once();session.unregisterService.assert_called_once_with(42)

    def test_release_failure_still_unregisters_callback(self):
        session=Mock();manager=Mock();session.registerService.return_value=42
        scope=EyeResources(session,manager);scope.acquire();manager.releaseResources.side_effect=RuntimeError('release')
        with self.assertRaises(RuntimeError):scope.release()
        session.unregisterService.assert_called_once_with(42)
