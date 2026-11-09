"""Export the findings shown on the Atlas Model page (site/data/model_findings.json) from the analysis outputs.

Only settled, historical findings go to the site. Seat-by-seat 2026 risk tables and projected seat counts stay in the
private analysis pages until nominations are final and the One Nation preference question is settled.

Inputs  data/analysis/{member_effects,cross_level,seat_loss,primary_swings,boundary_effects,returning_challengers,onp_effect,onp_flows,demog_change,weather_effects,astrology,afl_effects}.json
Output  site/data/model_findings.json
Usage   python3 -m src.export_model_findings
"""
import os, json, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = lambda n: json.load(open(os.path.join(ROOT, 'data/analysis', n + '.json')))


def main():
    me, cl, sl, ps, be, rc = (A(n) for n in ('member_effects', 'cross_level', 'seat_loss', 'primary_swings', 'boundary_effects', 'returning_challengers'))
    cats = ('sophomore_gain', 'sophomore_held', 'sophomore_byelection', 'open')
    T = me['tenure']['all']
    out = {'generated': dt.date.today().isoformat(),
           'members': {
               'all': {k: me['all'][k] for k in cats} | {'n': me['all']['n']}, 'state': {k: me['state'][k] for k in cats} | {'n': me['state']['n']},
               'federal': {k: me['federal'][k] for k in cats} | {'n': me['federal']['n']},
               'tenure': {k: T[k] for k in ('stand_3', 'stand_4', 'stand_5plus', 'open_1', 'open_2', 'open_3', 'open_4plus')} | {'counts': T['counts']},
               'member_value': T['member_value'], 'leaders': me['tenure'].get('leaders_summary'),
               'transferred': {'other_party': me['booth']['gap_other_party'], 'same_party': me['booth']['gap_same_party']},
               'outlook_2026': [{k: m[k] for k in ('seat', 'member', 'party', 'category', 'terms', 'retiring', 'not_on_declared_list', 'expected_pts')} for m in me['outlook_2026']]},
           'two_levels': {p: {'xs': cl['split_tickets'][p]['within_federal_division']['xs'], 'xf': cl['split_tickets'][p]['within_state_district']['xf'],
                              'ind_fed': cl['split_tickets'][p]['pooled']['ind_fed']} for p in ('ALP', 'COAL')} |
                         {'federal_member_change': cl['federal_member_changes']['ALP']['member_only']['dmem'], 'headwind': cl['statewide']},
           'challengers': {'second_go': rc['vote']['ALP+COAL']['second_v_member'], 'v_member_who_beat_them': rc['vote']['ALP+COAL']['v_first_term_member_who_won_it'],
                           'winning': {k: rc['winning'][k] for k in ('n', 'wins', 'returning_odds_ratio', 'returning_ci', 'open_odds_ratio', 'open_ci')},
                           'win_rates': rc['win_rates'], 'rematch_member': rc['member_side']['returning_challenger'], 'former_members': {k: rc['former_members'][k] for k in ('n_former', 'former_won')},
                           'independents': rc['independents']},
           'pendulum': {k: sl[k] for k in ('n', 'losses', 'base', 'by_margin', 'lost_to', 'notional_check', 'swing_by_election')} |
                       {'predictors': [{k: p[k] for k in ('key', 'label', 'odds_ratio', 'lo', 'hi', 'loeo_gain', 'continuous', 'per')} for p in sl['predictors']],
                        'surprises': [{k: r[k] for k in ('to', 'seat', 'member', 'party', 'margin', 'swing', 'p_lose', 'lost_to')} for r in sl['upsets_lost'][:8]]},
           'swings': {'rules': {g: {k: ps['rules'][g][k] for k in ('n', 'lambda', 'rmse_uniform', 'rmse_proportional', 'rmse_lambda_out_of_sample')} for g in ('ALP', 'COAL', 'GRN', 'MINOR')},
                      'onp': ps['onp_senate']['fed2022->fed2025'],
                      'backtest': {k: {x: v[x] for x in ('seats', 'primaries', 'two_party')} for k, v in ps['backtest'].items()}},
           'boundaries': {'check': {e: {k: be['check'][e][k] for k in ('seats', 'mean_diff', 'mean_abs_diff', 'within_1pt', 'rows')} for e in ('vic2022', 'fed2025')} | {'source': be['check']['source']},
                          'redistributions': [{k: r[k] for k in ('for', 'seats', 'abolished', 'created', 'median_from_namesake', 'mean_abs_shift_pts', 'notional_flips', 'flips_won_by_notional_party')} for r in be['redistributions']],
                          'flips': be['flips'], 'flips_summary': be['flips_summary'],
                          'territory': {k: be['territory'][k] for k in ('n', 'other_party_pts_per_100pct', 'other_ci', 'same_party_pts_per_100pct', 'same_ci')}}}
    # One Nation: history and method only (no 2026 seat readings)
    oe, of = A('onp_effect'), A('onp_flows')
    out['onp'] = {'senate_statewide': oe['senate_statewide'], 'lc2022_statewide': oe['lc2022_statewide'], 'map_correlations': oe['map_correlations'],
                  'level': {'venues': oe['level']['venues'], 'cv_r2': oe['level']['cv_r2'], 'coef': oe['level']['coef'][:10]},
                  'takes_from': oe['takes_from'],
                  'surges': of['surges'],
                  'flows': {k: of['pooled'][k] for k in ('LIB', 'NAT', 'GRN', 'ALP', 'IND', 'OTH', 'ONP>LIB/ALP', 'ONP>NAT/ALP') if k in of['pooled']},
                  'n_observations': of['n_observations'], 'n_elections': len(of['by_election']),
                  'validation_sa2026': {k: v for k, v in of['validation_sa2026'].items() if k != 'pooled_ratios_used'}}
    # the changing map: realignment gradients and composition (src.demog_change)
    dc = A('demog_change'); dd = dc['decomposition_2006_2022']
    import numpy as np
    comp = {}
    for pty in ('ALP', 'COAL', 'GRN'):
        rows = [r for r in dd['districts'] if pty in r and r['venues'] >= 5]
        rel = np.array([r[pty]['change'] - r[pty]['statewide'] for r in rows]); cr = np.array([r[pty]['composition_rel'] for r in rows])
        srt = sorted(rows, key=lambda r: -r[pty]['composition_rel'])
        pick = lambda r: {'seat': r['seat'], 'composition': r[pty]['composition_rel'], 'change': r[pty]['change'], 'statewide': r[pty]['statewide']}
        comp[pty] = {'share_explained': round(float(np.corrcoef(cr, rel)[0, 1] ** 2), 3), 'seats': len(rows),
                     'helped': [pick(r) for r in srt[:5]], 'hurt': [pick(r) for r in srt[-5:][::-1]]}
    ex = {r['seat']: r['pop_change'] for r in dd['districts'] if r['seat'] in ('Brunswick', 'Melton', 'Tarneit', 'Kew')}
    out['changing_map'] = {'bivariate': dc['bivariate'], 'holdout_2018_2022': dc['holdout_2018_2022'], 'venue_elections': dc['venue_elections'],
                           'composition_2006_2022': comp, 'venues_2006_2022': dd['venues'], 'examples': ex,
                           'melton': {k: next(r for r in dd['districts'] if r['seat'] == 'Melton')['ALP'][k] for k in ('change', 'statewide', 'composition_rel')}}
    # things that don't matter (we checked): weather, the sky, the footy
    def by_club(am):
        """each club: how many of its group x margin correlations reach p < 0.05, and its strongest one"""
        out = {}
        for r in am['all']:
            c = out.setdefault(r['club'], {'club': r['club'], 'interstate': r['interstate'], 'tests': 0, 'p_below_05': 0, 'strongest': None})
            c['tests'] += 1; c['p_below_05'] += r['p'] < 0.05
            if c['strongest'] is None or r['p'] < c['strongest']['p']:
                c['strongest'] = {k: r[k] for k in ('outcome', 'group', 'r', 'p')}
        return sorted(out.values(), key=lambda c: (c['interstate'], c['strongest']['p']))
    we, ast, afl = A('weather_effects'), A('astrology'), A('afl_effects')
    out['trivia'] = {
        'weather': {'venue_elections': we['venue_elections'], 'median_station_km': we['median_station_km'], 'statewide': we['statewide'],
                    'effects': {k: we['effects'][k] for k in ('log_votes', 'informal', 'gov_opp', 'lab_coal', 'gov_sh', 'ALP_sh', 'COAL_sh', 'GRN_sh')},
                    'naive_gov_heat': we['naive_election_fe_only']['gov_sh'], 'naive_hot_day': we['naive_hot_day'], 'deluge': we['vic2010_deluge']},
        'sky': {'elections': [{k: r[k] for k in ('election', 'gov_primary_change', 'held_office', 'moon_sign', 'moon_illumination', 'mercury_retrograde', 'eclipse_within_14_days', 'friday_13th_in_campaign', 'jupiter_sign')} for r in ast['elections']],
                'n_tests': ast['n_tests'], 'nominal_hits': len(ast['nominal_hits']), 'expected_by_chance': ast['expected_by_chance'], 'surviving': len(ast['surviving_correction']),
                'best': sorted(ast['tests'], key=lambda t: t['p'])[:3], 'pseudo_replication': ast['pseudo_replication'],
                'moon_by_party': {k: ast['moon_by_party'][k] for k in ('elections', 'grid', 'n_tests', 'expected_by_chance', 'best', 'signs_untested')}
                                 | {'nominal_hits': len(ast['moon_by_party']['nominal_hits']), 'surviving_holm': len(ast['moon_by_party']['surviving_holm']), 'surviving_fdr': len(ast['moon_by_party']['surviving_fdr'])}},
        'weather_mood': {k: {'joint_p': v['joint']['placebo_p'], 'max_abs_t': v['joint']['max_abs_t'], 'placebo_median_max_t': v['joint']['placebo_max_abs_t_median'],
                             'strongest': max(v['groups'].items(), key=lambda kv: abs(kv[1]['t']))} for k, v in A('weather_mood')['results'].items()},
        'afl_mood': {k: v for k, v in A('afl_mood').items() if k in ('summary', 'top_victorian', 'top_interstate', 'surviving_fdr', 'elections', 'joint_shuffle', 'joint_shuffle_within_level')}
                    | {'by_club': by_club(A('afl_mood'))},
        'footy': {'effects': afl['effects'], 'geelong': afl['geelong'], 'geelong_summary': afl['geelong_summary'], 'randomisation': afl['won_last_game_randomisation'],
                  'premiers': {e: {'premier': t['premier'], 'runner_up': t['grand_final_loser']} for e, t in afl['elections'].items()}, 'area_venues': afl['area_venues']}}
    p = os.path.join(ROOT, 'site/data/model_findings.json')
    def clean(x):   # browsers reject NaN in JSON: missing values go out as null
        if isinstance(x, float) and (x != x or x in (float('inf'), float('-inf'))):
            return None
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [clean(v) for v in x]
        return x
    json.dump(clean(out), open(p, 'w'), separators=(',', ':'), allow_nan=False)
    print(f'{p}: {os.path.getsize(p) / 1024:.0f} KB')


if __name__ == '__main__':
    main()
