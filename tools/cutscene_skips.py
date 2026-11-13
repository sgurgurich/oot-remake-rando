"""Work out the cutscene edits behind the "skip intro" and "every cutscene skippable"
options, and survey whether cutscenes could be skipped automatically. Writes
data/cutscene_skips.json:

  intro            OpeningEvent link edits: Navi's wake-up scene (Dm_Kokiri_0030) is
                   bypassed through the branch the game uses when the player presses Skip,
                   then through an existing fade-in (the screen is faded out before it).
                   The narrated opening (Dm_Kokiri_0000) stays: it plays while Kokiri Forest
                   loads and the flow checks once that loading finished right after it, so
                   it is made skippable instead (see 'unlock').
  unlock           event setting component lists whose SkipSetting (DisableSkip) is removed.
                   Only three cutscenes disable the Skip button: the opening, the title, the
                   credits. The intro option unlocks the opening; the other option all three.
  auto_skip_survey why cutscenes are NOT bypassed automatically (rules below). Kept as
                   documentation; nothing applies it.

Survey rules, kept for when this is revisited:

    py tools/cutscene_skips.py          (needs Event/EventFlow and Banc extracted into work/raw)

Cutscenes (Dm_*) are timeline files started from event flows by an EventSystemActor
EventTransition action. A skip redirects whatever leads to that action (previous event,
switch case, fork branch or entry point) to the event after it. Only u16 event indices
change, so file sizes and offsets stay the same (see tools/evfl.py).

A call is only bypassed when all of these hold; anything else keeps its cutscene (which
the game already lets the player skip by hand):
  - the cutscene is a timeline that only uses presentation actions (camera, fades,
    voices, effects, animation, rumble, ...): nothing that warps, sets time, changes
    music state, starts boss battles or credits;
  - it is not a system scene (Dm_SY_*, DmF_*: item gets, ocarina, chests, bottles), a
    song lesson, the title or the credits;
  - no map or flow checks its HavePlayedEvent.<name> flag (a bypass never sets it);
  - the screen is visible afterwards: either nothing faded it out before the call, or a
    fade-in follows within a few events of where the flow continues.
If the flow checks EventQueryIsEventSkipedMostRecent right after the call, the bypass
goes to the "skipped" branch the developers wrote for players who press Skip.
"""
import glob, json, os, re, struct, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dump, zs, evfl, byml

ROM = dump.ROM
OUT = os.path.join(HERE, '..', 'data', 'cutscene_skips.json')

# Timeline actions that only affect what is shown or heard during the cutscene.
PRESENTATION = {
    'EventMemberCreateMethod', 'EventEventFadeInForTimeline', 'EventEventFadeOutForTimeline', 'EventWorldManagerController',
    'EventCamera', 'EventPlayASForTimeline', 'EventMoveCameraAnimationInstructions', 'EventGoOffstageForUser',
    'EventStartVoice', 'EventFlowMsg', 'EventSetDoFForTimeline', 'EventSetNearCurrentCameraAnimation',
    'EventEffectEmitter', 'EventNodeEffectEmit', 'EventControllerRumbleTimeline', 'EventTriggerChemicalRequestDryTemporarily',
    'EventTriggerPlayerTemporaryBootsChange', 'EventTriggerPlayerRestoreBootsChange', 'EventEffectAddELinkHiddenSetting',
    'EventDoNothing', 'EventEditLocationalLight', 'EventCreateLocationalLightToEventCenter', 'EventNodeEffectEmitOneShot',
    'EventEffectDeleteELinkHiddenSetting', 'EventTriggerParticipateEvent', 'EventShowDemoNicknameUIForTimeline',
    'EventNaviPlayLipSync', 'EventNaviStopLipSync', 'EventDemoProductSupportComment', 'EventResetToInGameParametersDoF',
    'EventModelBind', 'EventOverwriteSceneShadingParams', 'EventTriggerSetModelAlpha', 'EventTriggerStartFadeIn',
    'EventTriggerStartFadeOut', 'EventTriggerSetCharaReflectionCaustics', 'EventTriggerSetModelLodManual',
    'EventSetRenderingCenterPosFromCameraPos', 'EventTriggerChangeModelAlphaDrawTiming', 'EventTerrainCalcCenter',
    'EventNodeEffectFade', 'EventNodeSetPushRadius', 'EventTriggerSetFairyColor',
    'EventPreComputedCullingDisableUntilEventEndForTimeline', 'EventEditLocationalLightAmplifier',
    'EventTriggerWmThunderOneShot', 'EventTriggerEmitXLink', 'EventTriggerXLinkFadeByKey',
    'EventTriggerAddPreComputedCullingBasePos', 'EventClothRequestExtraWind', 'EventTriggerStartReplaceTexture',
    'EventSetDynamicResolutionLoadThreshold', 'EventPlayASAndModelBindForTimeline', 'EventSetCutChangeCopyFrameNum',
    'EventSoundReleaseDucking', 'EventTriggerSetStopEffect', 'EventTriggerPhysicsSetEnableClothParallel',
}
NEVER = re.compile(r'^(Dm_SY_|DmF_|Dm_MelodyGet_|Dm_StaffCredit|Dm_Title|Dm_Kokiri_0000$)')
SKIP_QUERY = 'EventQueryIsEventSkipedMostRecent'
LOOK = 10  # events to look through for fades


def fade(e):
    n = e.get('action_name') or ''
    if 'FadeOut' in n and 'Bgm' not in n: return 'out'
    if 'FadeIn' in n and 'Bgm' not in n: return 'in'
    return None


def is_cutscene_call(e):
    return (e.get('action_name') == 'EventTransition' and isinstance(e.get('params'), dict)
            and str(e['params'].get('EventName', '')).startswith('Dm_'))


def screen_before(f, i):
    """'visible', 'black' or None (unknown) right before event i, walking back through
    single-predecessor chains."""
    seen = set()
    for _ in range(LOOK):
        preds = [p for p in f.predecessors(i) if p[1] != 'entry']
        entry = any(p[1] == 'entry' for p in f.predecessors(i))
        if entry and not preds: return None
        if len(preds) != 1 or entry: return None
        j = preds[0][0]
        if j in seen: return None
        seen.add(j)
        e = f.events[j]
        if is_cutscene_call(e): return None
        fd = fade(e)
        if fd == 'out': return 'black'
        if fd == 'in': return 'visible'
        i = j
    return 'visible'


def fade_in_ahead(f, i):
    """True if, following plain next links from event i, a fade-in comes before any
    other cutscene, branch or end."""
    for _ in range(LOOK):
        if i == evfl.NONE: return False
        e = f.events[i]
        if fade(e) == 'in': return True
        if is_cutscene_call(e) or e['type'] in ('switch', 'fork'): return False
        i = e.get('next', evfl.NONE)
    return False


def timeline_actions():
    out = {}
    for p in glob.glob(os.path.join(ROM, 'Event', 'EventFlow', 'Dm_*.bfevfl.zs')):
        raw = zs.decompress(ROM, p)
        if struct.unpack_from('<H', raw, 0x20)[0] != 0: continue
        out[os.path.basename(p)[:-10]] = set(m.decode() for m in re.findall(rb'(?<![A-Za-z0-9_])Event[A-Z][A-Za-z0-9_]+', raw))
    return out


def checked_flags():
    """Cutscene names whose HavePlayedEvent flag appears in any flow or map."""
    names = set()
    pat = re.compile(rb'HavePlayedEvent\.(Dm_[A-Za-z0-9_]+)')
    for p in glob.glob(os.path.join(ROM, 'Event', 'EventFlow', '*.bfevfl.zs')) + glob.glob(os.path.join(ROM, 'Banc', '*', '*.bcett.byml.zs')):
        names.update(m.decode() for m in pat.findall(zs.decompress(ROM, p)))
    return names


def redirect_ops(f, i, target):
    """Edits that send everything leading to event i to `target` instead, or None if
    some predecessor cannot take that target."""
    ops = []
    for src, how in f.predecessors(i):
        if how == 'next':
            ops.append(['next', src, i, target])
        elif how.startswith('case'):
            ops.append(['case', src, int(how[4:]), i, target])
        elif how == 'entry':
            if target == evfl.NONE: return None
            ops.append(['entry', src, i, target])
        else:  # fork branch: no safe way to end a branch early
            return None
    return ops


def intro_ops(f):
    """OpeningEvent: bypass Navi's wake-up scene (Dm_Kokiri_0030). Indices are checked
    against the expected events before use, and again when the edit is applied."""
    ev = {e['name']: e for e in f.events}
    by_i = f.events
    t1 = next(e for e in by_i if is_cutscene_call(e) and e['params']['EventName'] == 'Dm_Kokiri_0030')
    sw = by_i[t1['next']]
    assert sw.get('query_name') == SKIP_QUERY
    skipped = dict(sw['cases'])[1]          # Navi warp used when the player skips
    assert by_i[skipped].get('action_name') == 'EventTriggerNaviWarpToTargetPosAndRot'
    after_warp = by_i[skipped]['next']      # music check, then the rest of the scene
    fade_in = next(e for e in by_i if e.get('action_name') == 'EventEventFadeIn' and e.get('next') == after_warp)
    ops = redirect_ops(f, t1['i'], skipped)
    ops.append(['next', skipped, after_warp, fade_in['i']])  # screen was faded out before the scene
    return ops


def main():
    tl = timeline_actions()
    flagged = checked_flags()
    flows = {}
    report = collections.Counter()
    kept = collections.defaultdict(list)
    skipped_names = collections.Counter()
    for p in sorted(glob.glob(os.path.join(ROM, 'Event', 'EventFlow', '*.bfevfl.zs'))):
        raw = zs.decompress(ROM, p)
        if struct.unpack_from('<H', raw, 0x20)[0] == 0: continue
        f = evfl.Flow(raw)
        rel = os.path.relpath(p, ROM).replace(os.sep, '/')
        ops = []
        for e in f.events:
            if not is_cutscene_call(e): continue
            name = e['params']['EventName']
            report['calls'] += 1
            why = None
            if f.name == 'OpeningEvent': why = 'intro (separate option)'
            elif NEVER.match(name): why = 'system scene, song, title or credits'
            elif name not in tl: why = 'not a plain timeline'
            elif tl[name] - PRESENTATION: why = 'changes game state: ' + ', '.join(sorted(tl[name] - PRESENTATION)[:3])
            elif name in flagged: why = 'its HavePlayedEvent flag is checked elsewhere'
            if why:
                kept[why].append(name); continue
            target = e['next']
            if target != evfl.NONE and f.events[target].get('query_name') == SKIP_QUERY:
                target = dict(f.events[target]['cases']).get(1, evfl.NONE)
            state = screen_before(f, e['i'])
            if state != 'visible' and not fade_in_ahead(f, target):
                kept['screen could stay black'].append(name); continue
            r = redirect_ops(f, e['i'], target)
            if r is None:
                kept['called from a parallel branch'].append(name); continue
            ops += r
            skipped_names[name] += 1
        if ops:
            flows[rel] = ops
    opening = 'Event/EventFlow/OpeningEvent.bfevfl.zs'
    intro = {opening: intro_ops(evfl.Flow(zs.decompress(ROM, os.path.join(ROM, opening))))}
    unlock = {}
    for p in sorted(glob.glob(os.path.join(ROM, 'Event', 'EventSetting', 'EventSettingComponentList', '*.bgyml'))):
        comps = byml.load(open(p, 'rb').read()).get('Components') or {}
        if 'SkipSetting' in comps:
            unlock[os.path.relpath(p, ROM).replace(os.sep, '/')] = os.path.basename(p).split('.')[0]
    data = {'intro': intro, 'unlock': unlock,
            'intro_unlock': [r for r, n in unlock.items() if n == 'Dm_Kokiri_0000'],
            'auto_skip_survey': {'calls': report['calls'], 'would_bypass': sum(skipped_names.values()),
                                 'bypassable_cutscenes': sorted(skipped_names),
                                 'kept': {k: sorted(set(v)) for k, v in kept.items()}}}
    json.dump(data, open(OUT, 'w', encoding='utf-8'), indent=1)
    print('intro edits:', intro)
    print('skip-locked cutscenes:', unlock)
    print('survey: %d cutscene calls in flows; only %d would pass every rule for an automatic skip'
          % (report['calls'], sum(skipped_names.values())))
    for k, v in kept.items(): print('  kept, %s: %d' % (k, len(v)))
    print('wrote', OUT)


if __name__ == '__main__':
    main()
