"""Export the findings shown on the Atlas Model page (site/data/model_findings.json) from the analysis outputs.

Only settled, historical findings go to the site. Seat-by-seat 2026 risk tables and projected seat counts stay in the
private analysis pages until nominations are final and the One Nation preference question is settled.

Inputs  data/analysis/{member_effects,cross_level,seat_loss,primary_swings,boundary_effects,returning_challengers,onp_effect,onp_flows}.json
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
    p = os.path.join(ROOT, 'site/data/model_findings.json')
    json.dump(out, open(p, 'w'), separators=(',', ':'))
    print(f'{p}: {os.path.getsize(p) / 1024:.0f} KB')


if __name__ == '__main__':
    main()
