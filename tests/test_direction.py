import unittest
import numpy as np
from app.direction import plan_intents,MANUAL_NAMES,direct_motion
from app.robot_plan import build_plan,bezier_bounds
from app.plan_preview import sample_plan,speech_preview
from app.motion_quality import analyze_telemetry
from nao_gestures.kinematics import REST,NAMES

def speech(tokens):
    return {'text':' '.join(tokens),'duration_s':len(tokens)*1.6+1,
            'words':[{'text':w.strip('!?.,'),'start_s':i*1.6+.1,'duration_s':.4} for i,w in enumerate(tokens)]}

class DirectionTests(unittest.TestCase):
    def test_continuous_hands_follow_emage_without_keyword_events(self):
        t=np.arange(241)/30
        q=np.tile([.95,.24,-1.1,-.75,.95,-.24,1.1,.75],(len(t),1))
        q[:,0]+=.4*np.sin(2*np.pi*t/4)
        q[:,3]+=.3*np.sin(2*np.pi*t/4)
        directed,_,manual=direct_motion(q,None,t,{'events':[]})
        np.testing.assert_allclose(directed,q)
        self.assertGreater(np.ptp(manual[:,2]),.12)
        self.assertGreater(np.ptp(manual[:,0]),.1)
        # A stationary other arm is not given an arbitrary periodic motion.
        self.assertLess(np.ptp(manual[:,3]),1e-10)
        self.assertTrue(np.all((manual[:,2:]>=.25)&(manual[:,2:]<=.91)))

    def test_intent_preserves_passive_arm_and_most_of_source(self):
        t=np.arange(241)/30
        q=np.tile([.95,.24,-1.1,-.75,.95,-.24,1.1,.75],(len(t),1))
        q[:,0]+=.4*np.sin(t);q[:,4]+=.4*np.cos(t)
        directed,_,_=direct_motion(q,None,t,{'events':[{'kind':'greeting','side':'L','at_s':2.}]})
        np.testing.assert_allclose(directed[:,4:],q[:,4:])
        self.assertLess(np.abs(directed-q).max(),.1)

    def test_intents_use_timed_words_and_alternate_contrast(self):
        data=speech(['Olá','primeiro','segundo','importante','certo?'])
        events=plan_intents(data)['events']
        self.assertIn('greeting',[e['kind'] for e in events])
        self.assertEqual([e['side'] for e in events if e['kind']=='contrast'],['L','R'])
        self.assertIn('question',[e['kind'] for e in plan_intents(speech(['O','que','voce','acha?']))['events']])
        for event in events:
            word=next(w for w in data['words'] if w['text']==event['word'])
            self.assertAlmostEqual(event['at_s'],word['start_s']+.2)

    def test_explicit_hand_commands_negation_and_idiom(self):
        opened=plan_intents(speech(['Vou','abrir','a','mão']))['events']
        closed=plan_intents(speech(['Vou','fechar','a','mão']))['events']
        negated=plan_intents(speech(['Não','feche','a','mão']))['events']
        idiom=plan_intents(speech(['Vou','abrir','mão','de','algo']))['events']
        self.assertIn('open',[e['kind'] for e in opened])
        self.assertIn('close',[e['kind'] for e in closed])
        self.assertNotIn('close',[e['kind'] for e in negated])
        self.assertNotIn('open',[e['kind'] for e in idiom])

    def test_missing_timestamps_are_not_invented(self):
        with self.assertRaises(ValueError):plan_intents({'text':'Olá','duration_s':3,'words':[]})
        data=speech(['Olá']);data['words'][0]['start_s']=float('nan')
        with self.assertRaises(ValueError):plan_intents(data)

    def test_unknown_clause_has_one_explanatory_event(self):
        plan=plan_intents(speech(['O','tempo','passou','rapidamente']))
        self.assertEqual(len(plan['events']),1)
        self.assertTrue(plan['events'][0]['fallback'])

    def fixture(self,head=True):
        t=np.arange(241)/30;q=np.tile(REST,(len(t),1))
        trajectory={'joint_names':NAMES,'times_s':t.tolist(),'angles_rad':q.tolist(),'interpolation':'uniform_cubic_control_points'}
        direction={'method':'test vocabulary','events':[{'kind':'greeting','side':'L','at_s':1.5},{'kind':'close','side':'both','at_s':4.8}]}
        plan=build_plan(trajectory,REST,head_targets=np.zeros((len(t),2)) if head else None,current_head=[0.,0.] if head else None,
                        direction=direction,current_manual=[0.,0.,.02,.02])
        plan['initial_angles']=REST.tolist()+([0.,0.] if head else [])+[0.,0.,.02,.02]
        return plan

    def test_full_plan_opens_closes_and_returns_without_mixed_units(self):
        plan=self.fixture();self.assertEqual(len(plan['names']),14)
        self.assertEqual(plan['names'][-4:],MANUAL_NAMES)
        self.assertEqual(plan['scope'],'arms_head_hands')
        self.assertEqual(plan['joint_units'][-2:],['open_fraction','open_fraction'])
        self.assertEqual(plan['gesture_range_deg'][-2:],[None,None])
        values=sample_plan(plan,np.array([plan['audio_start_s']+1.5,plan['audio_start_s']+4.8,plan['duration_s']]))
        self.assertGreater(values[0,-2],values[1,-2]+.2)
        np.testing.assert_allclose(values[-1,-4:],[0.,0.,.02,.02],atol=1e-12)
        bounds=bezier_bounds(plan)
        self.assertLessEqual(bounds['hand_velocity_bound_fraction_s'],1.001)
        self.assertLessEqual(bounds['hand_acceleration_bound_fraction_s2'],3.001)

    def test_intent_without_head_preserves_safe_scope_and_speech_clock(self):
        plan=self.fixture(head=False);self.assertEqual(len(plan['names']),12)
        self.assertEqual(plan['scope'],'arms_hands');self.assertFalse(plan['head_enabled'])
        preview=speech_preview(plan)
        self.assertAlmostEqual(preview['times_s'][-1],plan['speech_duration_s'])
        self.assertEqual(len(preview['angles_rad'][0]),12)

    def test_hand_tracking_is_percentage_and_excluded_from_degree_rms(self):
        rows=[{'elapsed_s':i*.1,'commanded':[.1,.4],'measured':[0.,.5]} for i in range(4)]
        result=analyze_telemetry(rows,['HeadYaw','LHand'])
        self.assertAlmostEqual(result['tracking_rms_deg'],np.degrees(.1))
        self.assertAlmostEqual(result['hand_tracking_rms_percent'],10.)
        self.assertNotIn('tracking_rms_deg',result['joints']['LHand'])

if __name__=='__main__':unittest.main()
