"""Census indicators for the 2022 Victorian districts and for every election-day booth catchment on those
boundaries, built from the ABS SA1 DataPacks (2021 General Community Profile; 2016 GCP; 2011 Basic Community
Profile) with the SA1 -> district / catchment area weights from src/sa1_weights.py.

Each indicator is a numerator and a denominator summed over SA1s (weighted by the share of the SA1 inside the
target), then divided: shares are exact aggregates of the small-area counts, not averages of rates. Medians
(G02 / B02) cannot be summed, so they are population-weighted means of the SA1 medians, ignoring SA1s with no
figure; they are labelled as such. Column names in the DataPacks are stable across the three censuses for most
tables, with the differences handled in SPEC below; an indicator missing from a census is simply absent for it.

Inputs  raw/abs/datapacks/csv/<year>/*.csv      the extracted DataPack tables
        raw/abs/sa1_weights_<year>.json          SA1 -> district / booth weights
        site/data/booths.json.gz                 booth -> venue mapping (booth files are keyed by venue)
Outputs raw/abs/sa1_census_<year>.json           {indicators, state, districts, booths(by venue)} per census
Usage   python3 -m src.load_sa1_census [2021 2016 2011]; then src.build_demog assembles the site files.
"""
import sys, os, re, json, gzip, glob, csv
from collections import defaultdict
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YEARS = ('2021', '2016', '2011')
# table family -> DataPack table code per census (2021, 2016, 2011)
TAB = {'persons': ('G01', 'G01', 'B01'), 'medians': ('G02', 'G02', 'B02'), 'age': ('G04', 'G04', 'B04'), 'ancestry': ('G08', 'G08', 'B08'),
       'birthplace': ('G09', 'G09', 'B09'), 'language': ('G13', 'G13', 'B13'), 'religion': ('G14', 'G14', 'B14'), 'attending': ('G15', 'G15', 'B15'),
       'pincome': ('G17', 'G17', 'B17'), 'assist': ('G18', 'G18', 'B18'), 'volunteer': ('G23', 'G19', 'B19'), 'family': ('G29', 'G25', 'B25'),
       'hincome': ('G33', 'G29', 'B28'), 'vehicles': ('G34', 'G30', 'B29'), 'structure': ('G36', 'G32', 'B31'), 'tenure': ('G37', 'G33', 'B32'),
       'labour': ('G46', 'G43', 'B42'), 'qual': ('G49', 'G46', 'B40'), 'industry': ('G54', 'G51', 'B43'), 'occupation': ('G60', 'G57', 'B45'), 'travel': ('G62', 'G59', 'B46')}

# column expressions: "family:regex" (regex fullmatch on the column name; several columns may match and are summed)
# a tuple gives one expression per census in YEARS order; None means not available that census
SPEC = []   # (id, group, label, kind, numerator expr(s), denominator expr)


def ind(id_, group, label, num, den, kind='share'):
    SPEC.append((id_, group, label, kind, num if isinstance(num, list) else [num], den))


POP = 'persons:Tot_P_P'
ind('population', 'Population', 'Population', POP, None, 'count')
ind('age_median', 'Age', 'Median age', 'medians:Median_age_persons', POP, 'years')
AGEB = {'age_0_17': (list(range(0, 18)), 'Under 18'), 'age_15_24': (list(range(15, 25)), '15 to 24'), 'age_25_34': (list(range(25, 35)), '25 to 34'),
        'age_35_49': (list(range(35, 50)), '35 to 49'), 'age_50_64': (list(range(50, 65)), '50 to 64')}
for id_, (yrs, label) in AGEB.items():
    ind(id_, 'Age', label, 'age:Age_yr_(' + '|'.join(map(str, yrs)) + ')_P', POP)
ind('age_65_plus', 'Age', '65 and over', 'age:Age_yr_(6[5-9]|7[0-9]|80_84|85_89|90_94|95_99|100_yr_over)_P', POP)
# model inputs (adults by broad band) kept as ordinary indicators
ind('adults_18_34', 'Age', 'Adults aged 18 to 34 (of adults)', 'age:Age_yr_(1[89]|2[0-9]|3[0-4])_P', 'age:Age_yr_(1[89]|[2-7][0-9]|80_84|85_89|90_94|95_99|100_yr_over)_P')
ind('adults_35_54', 'Age', 'Adults aged 35 to 54 (of adults)', 'age:Age_yr_(3[5-9]|4[0-9]|5[0-4])_P', 'age:Age_yr_(1[89]|[2-7][0-9]|80_84|85_89|90_94|95_99|100_yr_over)_P')
ind('adults_55_plus', 'Age', 'Adults aged 55 and over (of adults)', 'age:Age_yr_(5[5-9]|[67][0-9]|80_84|85_89|90_94|95_99|100_yr_over)_P', 'age:Age_yr_(1[89]|[2-7][0-9]|80_84|85_89|90_94|95_99|100_yr_over)_P')
# income
ind('income_personal_median', 'Income', 'Median weekly personal income', 'medians:Median_[Tt]ot_prsnl_inc_weekly', POP, 'dollars')
ind('income_family_median', 'Income', 'Median weekly family income', 'medians:Median_[Tt]ot_fam_inc_weekly', 'family:Total_F', 'dollars')
ind('income_household_median', 'Income', 'Median weekly household income', 'medians:Median_[Tt]ot_hhd_inc_weekly', 'hincome:Tot_Tot', 'dollars')
PI_DEN = 'pincome:P_Tot_Tot'
ind('income_personal_2000_plus', 'Income', 'Personal income $2,000+ a week', ('pincome:P_(2000_2999|3000_3499|3500_more)_Tot', 'pincome:P_(2000_2999|3000_more)_Tot', 'pincome:P_2000_more_Tot'), PI_DEN)
ind('income_personal_under_500', 'Income', 'Personal income under $500 a week', ('pincome:P_(Neg_Nil_income|1_149|150_299|300_399|400_499)_Tot', 'pincome:P_(Neg_Nil_income|1_149|150_299|300_399|400_499)_Tot', 'pincome:P_(Neg_Nil_income|1_199|200_299|300_399)_Tot'), PI_DEN)
HI_DEN = 'hincome:Tot_Tot'
ind('income_household_3000_plus', 'Income', 'Household income $3,000+ a week', 'hincome:HI_(3000_3499|3500_3999|4000_more)_Tot', HI_DEN)
ind('income_household_under_1000', 'Income', 'Household income under $1,000 a week', ('hincome:(Negative_Nil_income|HI_(1_149|150_299|300_399|400_499|500_649|650_799|800_999))_Tot', 'hincome:(Negative_Nil_income|HI_(1_149|150_299|300_399|400_499|500_649|650_799|800_999))_Tot', 'hincome:(Negative_Nil_income|HI_(1_199|200_299|300_399|400_599|600_799|800_999))_Tot'), HI_DEN)
ind('mortgage_median_monthly', 'Housing costs', 'Median monthly mortgage repayment', 'medians:Median_mortgage_repay_monthly', 'tenure:O_MTG_Total', 'dollars')
ind('rent_median', 'Housing costs', 'Median weekly rent', 'medians:Median_rent_weekly', 'tenure:R_Tot_Total', 'dollars')
# dwellings
ind('persons_per_bedroom', 'Dwellings', 'Persons per bedroom', 'medians:Average_num_psns_per_bedroom', 'hincome:Tot_Tot', 'ratio')
ind('household_size', 'Dwellings', 'Average household size', 'medians:Average_household_size', 'hincome:Tot_Tot', 'ratio')
ind('no_motor_vehicle', 'Dwellings', 'Households with no motor vehicle', 'vehicles:Num_MVs_per_dweling_0_MVs', 'vehicles:Num_MVs_per_dweling_Tot')
ind('two_plus_vehicles', 'Dwellings', 'Households with two or more vehicles', 'vehicles:Num_MVs_per_dweling_(2|3|4mo)_MVs', 'vehicles:Num_MVs_per_dweling_Tot')
ind('separate_house', 'Dwellings', 'Separate houses', 'structure:OPDs_Separate_house_Dwellings', 'structure:OPDs_Tot_OPDs_Dwellings')
ind('flat_apartment', 'Dwellings', 'Flats and apartments', 'structure:OPDs_Flt_(unit_)?apart_Tot_Dwgs', 'structure:OPDs_Tot_OPDs_Dwellings')
ind('townhouse', 'Dwellings', 'Townhouses and terraces', 'structure:OPDs_SD_r_t_h_th_Tot_Dwgs', 'structure:OPDs_Tot_OPDs_Dwellings')
ind('unoccupied_dwellings', 'Dwellings', 'Unoccupied dwellings (of all private dwellings)', 'structure:Unoccupied_PDs_Dwgs', 'structure:Total_PDs_Dwellings')
# birthplace
ind('born_australia', 'Birthplace', 'Born in Australia', 'persons:Birthplace_Australia_P', POP)
ind('born_overseas', 'Birthplace', 'Born overseas', 'persons:Birthplace_Elsewhere_P', POP)
COUNTRIES = [('born_new_zealand', 'New Zealand', 'New_Zealand'), ('born_england', 'England', ('England', 'England', 'UK_Channel_Islands_Isle_Man')), ('born_scotland', 'Scotland', ('Scotland', 'Scotland', None)),
             ('born_ireland', 'Ireland', 'Ireland'), ('born_italy', 'Italy', 'Italy'), ('born_malta', 'Malta', 'Malta'), ('born_bosnia_and_herzegovina', 'Bosnia and Herzegovina', ('Bosnia_Herzegov', 'Bosnia_Herzegov', 'Bosnia_Herzegovina')),
             ('born_croatia', 'Croatia', 'Croatia'), ('born_north_macedonia', 'North Macedonia', ('North_Macedonia', 'FYROM', 'Frmr_Yug_Repc_Mac_FYROM')), ('born_greece', 'Greece', 'Greece'), ('born_poland', 'Poland', 'Poland'),
             ('born_iran', 'Iran', ('Iran', 'Iran', None)), ('born_iraq', 'Iraq', 'Iraq'), ('born_lebanon', 'Lebanon', 'Lebanon'), ('born_turkey', 'Turkey', 'Turkey'), ('born_myanmar', 'Myanmar', ('Myanmar', 'Myanmar', None)),
             ('born_cambodia', 'Cambodia', 'Cambodia'), ('born_thailand', 'Thailand', 'Thailand'), ('born_vietnam', 'Vietnam', 'Vietnam'), ('born_indonesia', 'Indonesia', 'Indonesia'), ('born_malaysia', 'Malaysia', 'Malaysia'),
             ('born_philippines', 'Philippines', 'Philippines'), ('born_singapore', 'Singapore', 'Singapore'), ('born_china_excludes_sars_and_taiwan', 'China (excludes SARs and Taiwan)', ('China', 'China', 'China_excl_SARs_Taiwan')),
             ('born_hong_kong_sar_of_china', 'Hong Kong (SAR of China)', ('Hong_Kong_SAR_Ch', 'Hong_Kong', 'Hong_Kong_SAR_China')), ('born_taiwan', 'Taiwan', ('Taiwan', 'Taiwan', None)), ('born_korea_republic_of_south', 'Korea, Republic of (South)', ('Korea_South', 'Korea_South', 'Korea_Republic_South')),
             ('born_bangladesh', 'Bangladesh', ('Bangladesh', 'Bangladesh', None)), ('born_india', 'India', 'India'), ('born_nepal', 'Nepal', ('Nepal', 'Nepal', None)), ('born_pakistan', 'Pakistan', ('Pakistan', 'Pakistan', None)),
             ('born_sri_lanka', 'Sri Lanka', 'Sri_Lanka'), ('born_afghanistan', 'Afghanistan', ('Afghanistan', 'Afghanistan', None)), ('born_united_states_of_america', 'United States of America', ('USA', 'USA', 'United_States_America')),
             ('born_mauritius', 'Mauritius', ('Mauritius', 'Mauritius', None)), ('born_south_africa', 'South Africa', 'South_Africa'), ('born_germany', 'Germany', 'Germany'), ('born_netherlands', 'Netherlands', 'Netherlands')]
for id_, label, col in COUNTRIES:
    cols = col if isinstance(col, tuple) else (col, col, col)
    ind(id_, 'Birthplace: country', label, tuple((f'birthplace:P_{c}_Tot' if y != '2011' else f'birthplace:{c}_P') if c else None for y, c in zip(YEARS, cols)), ('birthplace:P_Tot_Tot', 'birthplace:P_Tot_Tot', 'birthplace:Tot_P'))
# ancestry (responses, of persons; people can give two)
ANC = [('ancestry_australian', 'Australian', 'Aust'), ('ancestry_australian_aboriginal', 'Australian Aboriginal', 'Aust_Abor'), ('ancestry_maori', 'Maori', 'Maori'), ('ancestry_new_zealander', 'New Zealander', 'NZ'),
       ('ancestry_samoan', 'Samoan', 'Samoan'), ('ancestry_english', 'English', 'English'), ('ancestry_scottish', 'Scottish', 'Scottish'), ('ancestry_irish', 'Irish', 'Irish'), ('ancestry_welsh', 'Welsh', 'Welsh'), ('ancestry_dutch', 'Dutch', 'Dutch'),
       ('ancestry_french', 'French', 'French'), ('ancestry_german', 'German', 'German'), ('ancestry_italian', 'Italian', 'Italian'), ('ancestry_maltese', 'Maltese', 'Maltese'), ('ancestry_spanish', 'Spanish', 'Spanish'),
       ('ancestry_croatian', 'Croatian', 'Croatian'), ('ancestry_greek', 'Greek', 'Greek'), ('ancestry_macedonian', 'Macedonian', 'Macedonian'), ('ancestry_serbian', 'Serbian', 'Serbian'), ('ancestry_hungarian', 'Hungarian', 'Hungarian'),
       ('ancestry_polish', 'Polish', 'Polish'), ('ancestry_russian', 'Russian', 'Russian'), ('ancestry_lebanese', 'Lebanese', 'Lebanese'), ('ancestry_turkish', 'Turkish', 'Turkish'), ('ancestry_vietnamese', 'Vietnamese', 'Vietnamese'),
       ('ancestry_filipino', 'Filipino', 'Filipino'), ('ancestry_chinese', 'Chinese', 'Chinese'), ('ancestry_korean', 'Korean', 'Korean'), ('ancestry_indian', 'Indian', 'Indian'), ('ancestry_sri_lankan', 'Sri Lankan', 'Sri_Lankan'),
       ('ancestry_south_african', 'South African', 'Sth_African')]
for id_, label, col in ANC:
    ind(id_, 'Ancestry', label, f'ancestry:{col}_Tot_[Rr]esp', POP)
ind('parents_both_overseas', 'Ancestry', 'Both parents born overseas', 'ancestry:Tot_P_BP_B_OS', 'ancestry:Tot_P_Tot_[Rr]esp')
# language
ind('speaks_english_only', 'Language', 'Speaks only English at home', 'persons:Lang_(used|spoken)_home_Eng_only_P', POP)
ind('other_language_home', 'Language', 'Speaks a language other than English at home', 'persons:Lang_(used|spoken)_home_Oth_Lang_P', POP)
ind('english_not_well', 'Language', 'Other language, speaks English not well or not at all', ('language:P_Tot_UOLSE_NWorNAA', 'language:P_Tot_SOLSE_NWorNAA', None), POP)
LANG = [('language_arabic', 'Arabic', ('Arabic', 'Arabic', 'Arabic')), ('language_chinese_cantonese', 'Chinese: Cantonese', ('CL_Canton', 'CL_Cantones', 'Chin_lang_Cant')), ('language_chinese_mandarin', 'Chinese: Mandarin', ('CL_Mandarin', 'CL_Mandarin', 'Chin_lang_Mand')),
        ('language_croatian', 'Croatian', 'Croatian'), ('language_french', 'French', 'French'), ('language_german', 'German', 'German'), ('language_greek', 'Greek', 'Greek'), ('language_indo_aryan_bengali', 'Indo-Aryan: Bengali', ('IAL_Bengali', 'IAL_Bengali', 'In_Ar_Lang_Beng')),
        ('language_indo_aryan_gujarati', 'Indo-Aryan: Gujarati', ('IAL_Guj', None, None)), ('language_indo_aryan_hindi', 'Indo-Aryan: Hindi', ('IAL_Hindi', 'IAL_Hindi', 'In_Ar_Lang_Hind')), ('language_indo_aryan_nepali', 'Indo-Aryan: Nepali', ('IAL_Nepali', None, None)),
        ('language_indo_aryan_punjabi', 'Indo-Aryan: Punjabi', ('IAL_Punjabi', 'IAL_Punjabi', 'In_Ar_Lang_Punj')), ('language_indo_aryan_sinhalese', 'Indo-Aryan: Sinhalese', ('IAL_Sinhal', 'IAL_Sinhalese', 'In_Ar_Lang_Sinh')), ('language_indo_aryan_urdu', 'Indo-Aryan: Urdu', ('IAL_Urdu', 'IAL_Urdu', 'In_Ar_Lang_Urdu')),
        ('language_italian', 'Italian', 'Italian'), ('language_japanese', 'Japanese', ('Japan', 'Japanese', 'Japanese')), ('language_khmer', 'Khmer', 'Khmer'), ('language_korean', 'Korean', 'Korean'), ('language_macedonian', 'Macedonian', ('Macedon', 'Macedonian', 'Macedonian')),
        ('language_malayalam', 'Malayalam', ('Malayalam', None, None)), ('language_persian_excluding_dari', 'Persian (excluding Dari)', ('Persian_ED', 'Persian_ED', 'Ir_La_Pe_excl_Da')), ('language_polish', 'Polish', 'Polish'), ('language_russian', 'Russian', 'Russian'),
        ('language_samoan', 'Samoan', 'Samoan'), ('language_serbian', 'Serbian', 'Serbian'), ('language_southeast_asian_austronesian_languages_filipino', 'Southeast Asian Austronesian languages: Filipino', ('SAL_Filipin', 'SAL_Filipino', 'Se_As_A_L_Filipino')),
        ('language_southeast_asian_austronesian_languages_indonesian', 'Southeast Asian Austronesian languages: Indonesian', ('SAL_Indon', 'SAL_Indonesian', 'Se_As_A_L_Indon')), ('language_southeast_asian_austronesian_languages_tagalog', 'Southeast Asian Austronesian languages: Tagalog', ('SAL_Tagalog', 'SAL_Tagalog', 'Se_As_A_L_Tagal')),
        ('language_spanish', 'Spanish', 'Spanish'), ('language_tamil', 'Tamil', 'Tamil'), ('language_thai', 'Thai', 'Thai'), ('language_turkish', 'Turkish', 'Turkish'), ('language_vietnamese', 'Vietnamese', 'Vietnamese')]
for id_, label, col in LANG:
    cols = col if isinstance(col, tuple) else (col, col, col)
    ind(id_, 'Language: spoken at home', label, tuple((f'language:POL_{c}_Tot' if y != '2011' else f'language:SOL_{c}_P') if c else None for y, c in zip(YEARS, cols)), POP)
# religion
REL = [('religion_buddhism', 'Buddhism', 'Buddhism_P'), ('religion_christianity_total', 'Christianity Total', 'Christianity_Tot_P'), ('religion_hinduism', 'Hinduism', 'Hinduism_P'), ('religion_islam', 'Islam', 'Islam_P'), ('religion_judaism', 'Judaism', 'Judaism_P'),
       ('religion_christian_nfd', 'Christian, nfd', 'Christianity_Christian_nfd_P'), ('religion_anglican', 'Anglican', 'Christianity_Anglican_P'), ('religion_baptist', 'Baptist', 'Christianity_Baptist_P'), ('religion_catholic', 'Catholic', 'Christianity_Catholic_P'),
       ('religion_lutheran', 'Lutheran', 'Christianity_Lutheran_P'), ('religion_oriental_orthodox', 'Oriental Orthodox', 'Christianity_Orintal_Orthdx_P'), ('religion_assyrian_apostolic', 'Assyrian Apostolic', 'Christianity_Asyrin_Apstlic_P'), ('religion_eastern_orthodox', 'Eastern Orthodox', 'Christianity_Eastrn_Orthdox_P'),
       ('religion_presbyterian_and_reformed', 'Presbyterian and Reformed', 'Christinty_Prsbytrin_Refrmd_P'), ('religion_uniting_church', 'Uniting Church', 'Christianity_Uniting_Church_P'), ('religion_pentecostal', 'Pentecostal', 'Christianity_Pentecostal_P'),
       ('religion_sikhism', 'Sikhism', ('Othr_Rel_Sikhism_P', 'Othr_Rel_Sikhism_P', None)), ('religion_other_religions_total', 'Other Religions Total', 'Other_Religions_Tot_P'),
       ('religion_no_religion_so_described', 'No Religion, so described', ('SB_OSB_NRA_NR_P', 'SB_OSB_NRA_NR_P', 'No_Religion_P')), ('religion_secular_other_spiritual_and_no_religious_affiliation_total', 'Secular Other Spiritual and No Religious Affiliation Total', ('SB_OSB_NRA_Tot_P', 'SB_OSB_NRA_Tot_P', 'No_Religion_P'))]
for id_, label, col in REL:
    cols = col if isinstance(col, tuple) else (col, col, col)
    ind(id_, 'Religion', label, tuple(f'religion:{c}' if c else None for c in cols), 'religion:Tot_P')
# education
ind('year12', 'Education', 'Completed Year 12 (of persons 15+)', 'persons:High_yr_schl_comp_Yr_12_eq_P', 'age:Age_yr_(1[5-9]|[2-7][0-9]|80_84|85_89|90_94|95_99|100_yr_over)_P')
QD = 'age:Age_yr_(1[5-9]|[2-7][0-9]|80_84|85_89|90_94|95_99|100_yr_over)_P'   # persons aged 15+, as the ABS does for attainment (G49's own total omits those without a qualification)
ind('bachelor_or_higher', 'Education', 'Bachelor degree or higher (of persons 15+)', 'qual:P_(PGrad_Deg|GradDip_and_GradCert|BachDeg)_Total', QD)
ind('postgraduate', 'Education', 'Postgraduate degree (of persons 15+)', 'qual:P_PGrad_Deg_Total', QD)
ind('certificate', 'Education', 'Certificate level (of persons 15+)', 'qual:P_Cert_Lev_Tot_Total', QD)
ind('diploma', 'Education', 'Advanced diploma or diploma (of persons 15+)', 'qual:P_AdvDip_and_Dip_Total', QD)
ind('students_university', 'Students, by type of institution', 'Attending university (of all students)', ('attending:Tert_Uni_other_high_edu_Tot_P', 'attending:Uni_other_Tert_Instit_Tot_P', 'attending:Uni_other_Tert_Instit_Tot_P'), 'attending:Tot_P')
ind('students_tafe', 'Students, by type of institution', 'Attending TAFE or other vocational (of all students)', ('attending:Tert_Voc_edu_Tot_P', 'attending:Tec_Furt_Educ_inst_Tot_P', 'attending:Tec_Furt_Educ_inst_Tot_P'), 'attending:Tot_P')
ind('students_secondary', 'Students, by type of institution', 'Attending secondary school (of all students)', ('attending:Secondary_Tot_Secondary_P', 'attending:Secondary_Tot_P', 'attending:Secondary_Tot_P'), 'attending:Tot_P')
ind('students_non_government_school', 'Students, by type of institution', 'School students at Catholic or other non-government schools (of school students)', ('attending:(Primary_Catholic|Primry_Othr_non_Govt|Secondary_Catholic|Secondary_Other_non_Govt)_P', 'attending:(Infants_Primary_Catholic|Infnts_Primry_Othr_Non_Govt|Secondary_Catholic|Secondary_Other_Non_Govt)_P', 'attending:(Infants_Primary_Catholic|Infnts_Primry_Othr_Non_Govt|Secondary_Catholic|Secondary_Other_Non_Govt)_P'), ('attending:(Primary_Tot_Primary|Secondary_Tot_Secondary)_P', 'attending:(Infants_Primary_Tot|Secondary_Tot)_P', 'attending:(Infants_Primary_Tot|Secondary_Tot)_P'))
# tenure
TD = 'tenure:Total_Total'
ind('owned_outright', 'Tenure', 'Owned outright', 'tenure:O_OR_Total', TD)
ind('owned_mortgage', 'Tenure', 'Owned with a mortgage', 'tenure:O_MTG_Total', TD)
ind('rented', 'Tenure', 'Rented', 'tenure:R_Tot_Total', TD)
ind('social_housing', 'Tenure', 'Social housing (public or community)', ('tenure:R_(ST_h_auth|Com_Hp)_Total', 'tenure:R_(ST_h_auth|Hse_coop_cty_ch_gp)_Total', 'tenure:R_(ST_h_auth|Hse_coop_cty_ch_gp)_Total'), TD)
# work
ind('unemployment_rate', 'Work', 'Unemployment rate (of the labour force)', ('labour:P_Tot_Unemp_Tot', 'labour:P_Tot_Unemp_Tot', 'labour:P_Unem_look_Tot_Tot'), 'labour:P_Tot_LF_Tot')
ind('participation_rate', 'Work', 'Labour force participation', 'labour:P_Tot_LF_Tot', 'labour:P_Tot_Tot')
ind('part_time_share', 'Work', 'Part-time (of the employed)', 'labour:P_Emp_PartT_Tot', 'labour:P_Emp_(FullT|PartT)_Tot')
OCC = [('occupation_managers', 'Managers', 'Managers'), ('occupation_professionals', 'Professionals', 'Professionals'), ('occupation_technicians_and_trades_workers', 'Technicians and Trades Workers', 'TechnicTrades_W'), ('occupation_community_and_personal_service_workers', 'Community and Personal Service Workers', 'CommunPersnlSvc_W'),
       ('occupation_clerical_and_administrative_workers', 'Clerical and Administrative Workers', 'ClericalAdminis_W'), ('occupation_sales_workers', 'Sales Workers', 'Sales_W'), ('occupation_machinery_operators_and_drivers', 'Machinery Operators and Drivers', 'Mach_oper_drivers'), ('occupation_labourers', 'Labourers', 'Labourers')]
for id_, label, col in OCC:
    ind(id_, 'Occupation', label, f'occupation:P_Tot_{col}', 'occupation:P_Tot_Tot')
INDU = [('industry_agriculture_forestry_and_fishing', 'Agriculture, Forestry and Fishing', 'Ag_For_Fshg'), ('industry_mining', 'Mining', 'Mining'), ('industry_manufacturing', 'Manufacturing', 'Manufact'), ('industry_electricity_gas_water_and_waste_services', 'Electricity, Gas, Water and Waste Services', 'El_Gas_Wt_Waste'),
        ('industry_construction', 'Construction', 'Constru'), ('industry_wholesale_trade', 'Wholesale Trade', 'WhlesaleTde'), ('industry_retail_trade', 'Retail Trade', 'RetTde'), ('industry_accommodation_and_food_services', 'Accommodation and Food Services', 'Accom_food'),
        ('industry_transport_postal_and_warehousing', 'Transport, Postal and Warehousing', 'Trans_post_wrehsg'), ('industry_information_media_and_telecommunications', 'Information Media and Telecommunications', 'Info_media_teleco'), ('industry_financial_and_insurance_services', 'Financial and Insurance Services', 'Fin_Insur'),
        ('industry_rental_hiring_and_real_estate_services', 'Rental, Hiring and Real Estate Services', 'RtnHir_REst'), ('industry_professional_scientific_and_technical_services', 'Professional, Scientific and Technical Services', 'Pro_scien_tec'), ('industry_administrative_and_support_services', 'Administrative and Support Services', 'Admin_supp'),
        ('industry_public_administration_and_safety', 'Public Administration and Safety', 'Public_admin_sfty'), ('industry_education_and_training', 'Education and Training', 'Educ_trng'), ('industry_health_care_and_social_assistance', 'Health Care and Social Assistance', 'HlthCare_SocAs'),
        ('industry_arts_and_recreation_services', 'Arts and Recreation Services', 'Art_recn'), ('industry_other_services', 'Other Services', 'Oth_scs')]
for id_, label, col in INDU:
    ind(id_, 'Industry', label, f'industry:P_{col}_Tot', 'industry:P_Tot_Tot')
# travel to work
TR = 'travel:Tot_P'
ind('travel_public_transport', 'Travel to work', 'Public transport (any)', 'travel:(One_method_(Train|Bus|Ferry)|One_met_Tram_(or|incl)_lt_rail|Two_methods_(Train|Bus)_Tot|Three_meth_(Tr_2_oth_meth|Trn_two_othr_met)|Three_met_Bs_2_ot_met_ex_tr)_P', TR)
ind('travel_car_driver', 'Travel to work', 'Car, as driver', 'travel:One_method_Car_as_driver_P', TR)
ind('worked_at_home', 'Travel to work', 'Worked at home', 'travel:Worked_home_P', TR)
ind('travel_bicycle', 'Travel to work', 'Bicycle', 'travel:One_method_Bicycle_P', TR)
ind('travel_walked', 'Travel to work', 'Walked only', 'travel:One_method_Walked_only_P', TR)
# health, community, families, population
ind('need_assistance', 'Health and community', 'Needs assistance with core activities', 'assist:P_Tot_Need_for_assistance', 'assist:P_Tot_Tot')
ind('volunteer', 'Health and community', 'Volunteers for an organisation or group', 'volunteer:P_Tot_Volunteer', 'volunteer:P_Tot_Tot')
ind('australian_citizens', 'Population', 'Australian citizens', 'persons:Australian_citizen_P', POP)
ind('indigenous', 'Population', 'Aboriginal and/or Torres Strait Islander', 'persons:Indigenous_P_Tot_P', POP)
# inputs for src/model_issues (hidden from the site's menus): household income bands, adults by age band, degree holders, tenure
HI_BANDS = {'2021': ['Negative_Nil_income', 'HI_1_149', 'HI_150_299', 'HI_300_399', 'HI_400_499', 'HI_500_649', 'HI_650_799', 'HI_800_999', 'HI_1000_1249', 'HI_1250_1499', 'HI_1500_1749', 'HI_1750_1999', 'HI_2000_2499', 'HI_2500_2999', 'HI_3000_3499', 'HI_3500_3999', 'HI_4000_more']}
for b in HI_BANDS['2021']:
    ind('mi_hhi_' + b.lower(), 'Model inputs', 'Households: ' + b, (f'hincome:{b}_Tot', None, None), None, 'count')
ind('mi_adults_18_34', 'Model inputs', 'Adults 18-34', 'age:Age_yr_(1[89]|2[0-9]|3[0-4])_P', None, 'count')
ind('mi_adults_35_54', 'Model inputs', 'Adults 35-54', 'age:Age_yr_(3[5-9]|4[0-9]|5[0-4])_P', None, 'count')
ind('mi_adults_55_plus', 'Model inputs', 'Adults 55+', 'age:Age_yr_(5[5-9]|[67][0-9]|80_84|85_89|90_94|95_99|100_yr_over)_P', None, 'count')
ind('mi_degree', 'Model inputs', 'Bachelor degree or higher (persons)', 'qual:P_(PGrad_Deg|GradDip_and_GradCert|BachDeg)_Total', None, 'count')
ind('mi_tenure_own', 'Model inputs', 'Owned outright (dwellings)', 'tenure:O_OR_Total', None, 'count')
ind('mi_tenure_mortgage', 'Model inputs', 'Owned with a mortgage (dwellings)', 'tenure:O_MTG_Total', None, 'count')
ind('mi_tenure_rent', 'Model inputs', 'Rented (dwellings)', 'tenure:R_Tot_Total', None, 'count')
ind('couple_families_with_children', 'Families', 'Couple families with children', 'family:CF_ChU15_a_Total_F', 'family:Total_F')
ind('one_parent_families', 'Families', 'One-parent families', 'family:OPF_Total_F', 'family:Total_F')
ind('couples_no_children', 'Families', 'Couples without children', 'family:CF_no_children_F', 'family:Total_F')


def load_headers(year):
    hdr = {}
    for f in sorted(glob.glob(os.path.join(ROOT, 'raw/abs/datapacks/csv', year, '*.csv'))):
        code = re.search(r'_([GB]\d+[A-Z]?)_', os.path.basename(f)).group(1)
        with open(f) as fh:
            hdr[code] = (f, fh.readline().rstrip('\n').split(','))
    return hdr


def resolve(year, hdr, expr):
    """'family:regex' -> [(file, column)] (all matching columns); leading '-' marks a column to subtract"""
    fam, rx = expr.split(':', 1)
    neg = rx.startswith('-')
    rx = rx[1:] if neg else rx
    code = TAB[fam][YEARS.index(year)]
    out = []
    for t, (f, cols) in hdr.items():
        if re.fullmatch(code + '[A-Z]?', t):
            out += [(f, c, neg) for c in cols[1:] if re.fullmatch(rx, c)]
    return out


def main(years):
    booths = json.load(gzip.open(os.path.join(ROOT, 'site/data/booths.json.gz')))
    venue_of = {r[2]: r[5] for r in booths['rows'] if r[0] in ('vic2022', 'vic2023n')}   # booth_id -> venue_id
    for year in years:
        yi = YEARS.index(year)
        hdr = load_headers(year)
        W = json.load(open(os.path.join(ROOT, f'raw/abs/sa1_weights_{year}.json')))['sa1']
        # resolve every expression to columns; collect columns to load per file
        plan, need = [], defaultdict(set)
        for id_, group, label, kind, nums, den in SPEC:
            nexprs = [(n[yi] if isinstance(n, tuple) else n) for n in nums]
            dexpr = den[yi] if isinstance(den, tuple) else den
            if any(n is None for n in nexprs) or (dexpr is None and kind != 'count'):
                continue
            ncols = [c for n in nexprs for c in resolve(year, hdr, n)]
            dcols = resolve(year, hdr, dexpr) if dexpr else []
            if not ncols or (dexpr and not dcols):
                print(f'   {year}: {id_} skipped (columns not found: {[n for n in nexprs if not resolve(year, hdr, n)] or dexpr})')
                continue
            plan.append((id_, group, label, kind, ncols, dcols))
            for f, c, _ in ncols + dcols:
                need[f].add(c)
        # load the columns
        data = {}   # (file, col) -> {sa1: value}
        for f, cols in need.items():
            with open(f) as fh:
                rd = csv.reader(fh); head = next(rd); idx = {c: head.index(c) for c in cols}
                store = {c: {} for c in cols}
                for row in rd:
                    code = row[0]
                    for c, i in idx.items():
                        v = row[i]
                        try:
                            store[c][code] = float(v)
                        except ValueError:
                            pass
            for c in cols:
                data[(f, c)] = store[c]
        # the 2016 and 2011 DataPacks key rows by the 7-digit SA1 code (state + last four of the SA2 + SA1): map the 11-digit boundary codes to it
        codes = set(k for d in data.values() for k in d)
        if codes and all(len(k) == 7 for k in list(codes)[:50]):
            seven = {}
            for m in list(W):
                s7 = m[0] + m[5:9] + m[9:11]
                if s7 in seven:
                    raise SystemExit(f'7-digit SA1 code clash: {m} and {seven[s7]}')
                seven[s7] = m
            W = {seven[s7]: W[seven[s7]] for s7 in seven}
            W = {s7: W[m] for s7, m in seven.items()}
        sa1s = sorted(codes & set(W))
        print(f'{year}: {len(plan)} indicators, {len(need)} tables, {len(sa1s)} SA1s matched to weights (of {len(W)} with weights)')
        # per-SA1 numerator / denominator vectors
        N, Dn = np.zeros((len(sa1s), len(plan))), np.zeros((len(sa1s), len(plan)))
        si = {s: i for i, s in enumerate(sa1s)}
        for j, (id_, group, label, kind, ncols, dcols) in enumerate(plan):
            if kind in ('years', 'dollars', 'ratio'):
                # a median: value * weight-base in the numerator, weight-base in the denominator (SA1s with no figure drop out)
                base = np.zeros(len(sa1s))
                for f, c, neg in dcols:
                    for s, v in data[(f, c)].items():
                        if s in si: base[si[s]] += v
                med = np.zeros(len(sa1s)); has = np.zeros(len(sa1s), dtype=bool)
                for f, c, neg in ncols:
                    for s, v in data[(f, c)].items():
                        if s in si and v > 0: med[si[s]] = v; has[si[s]] = True
                N[:, j] = np.where(has, med * base, 0); Dn[:, j] = np.where(has, base, 0)
            else:
                for f, c, neg in ncols:
                    for s, v in data[(f, c)].items():
                        if s in si: N[si[s], j] += -v if neg else v
                for f, c, neg in dcols:
                    for s, v in data[(f, c)].items():
                        if s in si: Dn[si[s], j] += v
        # aggregate
        def agg(key):
            accN, accD = defaultdict(lambda: np.zeros(len(plan))), defaultdict(lambda: np.zeros(len(plan)))
            for s in sa1s:
                for tid, w in W[s][key].items():
                    accN[tid] += w * N[si[s]]; accD[tid] += w * Dn[si[s]]
            return accN, accD
        def finish(accN, accD):
            out = {}
            for tid in accN:
                rec = {}
                for j, (id_, group, label, kind, ncols, dcols) in enumerate(plan):
                    if kind == 'count':
                        rec[id_] = int(round(float(accN[tid][j])))
                    elif accD[tid][j] > 0:
                        v = float(accN[tid][j] / accD[tid][j])
                        rec[id_] = round(v, 5 if kind == 'share' else 2)
                out[tid] = rec
            return out
        dN, dD = agg('d'); bN, bD = agg('b')
        districts = finish(dN, dD)
        booths_out = finish(bN, bD)
        # booth file keyed by venue (what the site uses across elections); keep the catchment booth id too
        by_venue = {}
        for bid, rec in booths_out.items():
            vid = venue_of.get(bid)
            if vid:
                by_venue[vid] = {'booth_id': bid, **rec}
        sN = N.sum(axis=0); sD = Dn.sum(axis=0)
        state = {}
        for j, (id_, group, label, kind, ncols, dcols) in enumerate(plan):
            state[id_] = int(round(float(sN[j]))) if kind == 'count' else (round(float(sN[j] / sD[j]), 5 if kind == 'share' else 2) if sD[j] > 0 else None)
        obj = {'census': int(year), 'boundaries': 'vic_la_2022',
               'source': f'ABS Census {year} SA1 DataPack ({"General" if year != "2011" else "Basic"} Community Profile), aggregated onto the 2022 Victorian districts and the 2022 election-day booth catchments by the share of each SA1 inside them',
               'indicators': [{'id': id_, 'group': group, 'label': label, 'kind': kind, **({'hidden': True} if id_.startswith('mi_') else {})} for id_, group, label, kind, _, _ in plan],
               'state': state, 'districts': districts, 'booths': by_venue}
        out = os.path.join(ROOT, f'raw/abs/sa1_census_{year}.json')
        json.dump(obj, open(out, 'w'), separators=(',', ':'))
        print(f'   {len(districts)} districts, {len(by_venue)} booth venues, state population {state.get("population")} -> {out}')


if __name__ == '__main__':
    main(sys.argv[1:] or list(YEARS))
