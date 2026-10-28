"""Measure tracking and unexpected pauses from recorded joint telemetry.

Angles in the input are radians. Results are JSON-compatible and use degrees.
This module does not import the robot SDK or send commands. A detected pause is
an observation, not a diagnosis of its mechanical or software cause.
"""
import argparse
import json
import math
from pathlib import Path


def analyze_telemetry(records, joint_names=None, speech_bounds=None,
                      pause_sensor_deg=.15, min_pause_s=.20,
                      min_command_travel_deg=.8, max_sample_gap_s=.30):
    """Return per-joint ranges, RMS tracking error and unplanned pause events.

    A pause requires at least three samples with measured range below
    ``pause_sensor_deg``, lasting at least ``min_pause_s``, while the command
    travels at least ``min_command_travel_deg``. Command travel is the sum of
    absolute increments. A planned stationary gesture therefore does not count.
    Samples separated by a gap above ``max_sample_gap_s`` cannot form a pause.

    ``speech_bounds=(start_s, end_s)`` restricts the analysis to the speech
    section and can exclude the entry and return transitions. The function does
    not guess these bounds from the motion. Timestamps must be strictly rising.
    """
    options=(pause_sensor_deg,min_pause_s,min_command_travel_deg,max_sample_gap_s)
    if not all(math.isfinite(float(x)) and float(x)>0 for x in options):
        raise ValueError('Pause thresholds must be finite and positive.')
    rows=list(records)
    if not rows:
        raise ValueError('Telemetry contains no samples.')
    count=len(rows[0].get('commanded',[]))
    if not count:
        raise ValueError('Telemetry contains no joints.')
    names=list(joint_names) if joint_names is not None else ['joint_%d'%j for j in range(count)]
    if len(names)!=count or len(set(names))!=count:
        raise ValueError('Joint names must be unique and match the telemetry.')
    times=[];commands=[];measured=[]
    for row in rows:
        try:
            at=float(row['elapsed_s'])
            commanded=[float(x) for x in row['commanded']]
            sensed=[float(x) for x in row['measured']]
        except (KeyError,TypeError,ValueError) as error:
            raise ValueError('Invalid telemetry sample.') from error
        if len(commanded)!=count or len(sensed)!=count or not all(math.isfinite(x) for x in [at]+commanded+sensed):
            raise ValueError('Telemetry must have finite angles and a consistent joint count.')
        if times and at<=times[-1]:
            raise ValueError('Telemetry timestamps must be strictly increasing.')
        times.append(at);commands.append(commanded);measured.append(sensed)
    if speech_bounds is not None:
        if len(speech_bounds)!=2 or not all(math.isfinite(float(x)) for x in speech_bounds) or speech_bounds[1]<speech_bounds[0]:
            raise ValueError('Invalid speech bounds.')
        selected=[k for k,at in enumerate(times) if speech_bounds[0]-1e-9<=at<=speech_bounds[1]+1e-9]
        if not selected:
            raise ValueError('No telemetry samples within the speech bounds.')
        times=[times[k] for k in selected]
        commands=[commands[k] for k in selected]
        measured=[measured[k] for k in selected]
    degrees=180./math.pi
    joints={};all_squared_error=[];hand_squared_error=[]
    for j,name in enumerate(names):
        is_hand=name in ('LHand','RHand');factor=100. if is_hand else degrees
        sensor_threshold=1.5 if is_hand else pause_sensor_deg
        travel_threshold=8. if is_hand else min_command_travel_deg
        suffix='percent' if is_hand else 'deg'
        c=[row[j]*factor for row in commands]
        q=[row[j]*factor for row in measured]
        squared_error=[(a-b)**2 for a,b in zip(c,q)]
        (hand_squared_error if is_hand else all_squared_error).extend(squared_error)
        pauses=[]

        def finish(first,last):
            if last-first<2:
                return
            duration=times[last]-times[first]
            travel=sum(abs(c[k]-c[k-1]) for k in range(first+1,last+1))
            if duration+1e-9>=min_pause_s and travel+1e-9>=travel_threshold:
                pauses.append({'start_s':times[first],'end_s':times[last],
                               'duration_s':duration,'command_travel_'+suffix:travel,
                               'sensor_range_'+suffix:max(q[first:last+1])-min(q[first:last+1])})

        first=0;low=high=q[0]
        for k in range(1,len(times)):
            next_low=min(low,q[k]);next_high=max(high,q[k])
            # A large timestamp gap means the intervening motion is unknown.
            if times[k]-times[k-1]>max_sample_gap_s or next_high-next_low>=sensor_threshold:
                finish(first,k-1)
                first=k;low=high=q[k]
            else:
                low=next_low;high=next_high
        finish(first,len(times)-1)
        joints[name]={'commanded_range_'+suffix:max(c)-min(c),
                      'measured_range_'+suffix:max(q)-min(q),
                      'tracking_rms_'+suffix:math.sqrt(sum(squared_error)/len(squared_error)),
                      'unit':'percent_open' if is_hand else 'degrees',
                      'pause_count':len(pauses),
                      'pause_duration_s':sum(p['duration_s'] for p in pauses),
                      'pauses':pauses}
    events=[p for joint in joints.values() for p in joint['pauses']]
    return {'schema':'nao-motion-quality-v1','sample_count':len(times),
            'window_s':[times[0],times[-1]],
            'speech_bounds_s':list(speech_bounds) if speech_bounds is not None else None,
            'thresholds':{'pause_sensor_deg':pause_sensor_deg,'min_pause_s':min_pause_s,
                          'min_command_travel_deg':min_command_travel_deg,'max_sample_gap_s':max_sample_gap_s},
            'tracking_rms_deg':math.sqrt(sum(all_squared_error)/len(all_squared_error)) if all_squared_error else None,
            'hand_tracking_rms_percent':math.sqrt(sum(hand_squared_error)/len(hand_squared_error)) if hand_squared_error else None,
            'unplanned_pause_count':len(events),
            'max_unplanned_pause_s':max((p['duration_s'] for p in events),default=0.),
            'pause_total_joint_s':sum(p['duration_s'] for p in events),
            'joints':joints}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('telemetry',type=Path)
    parser.add_argument('--start',type=float)
    parser.add_argument('--end',type=float)
    parser.add_argument('--names',nargs='+')
    args=parser.parse_args()
    if (args.start is None)!=(args.end is None):
        parser.error('Use --start and --end together.')
    rows=[json.loads(line) for line in args.telemetry.read_text(encoding='utf-8').splitlines() if line.strip()]
    bounds=None if args.start is None else (args.start,args.end)
    print(json.dumps(analyze_telemetry(rows,args.names,bounds),ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
