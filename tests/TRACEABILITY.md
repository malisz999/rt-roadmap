# Traceability: RS acceptance tests → tests

Generated from the `test_at_<nn>_` function names (ADS 10.4); `tests/acceptance/test_at_traceability.py` fails when an AT has no test or this table is stale.

AT-25 is partly manual: the automated test checks the structure (sticky CSS, legend, warnings panel, footer, A3 print rules) of EX, WE and DE; the visual review in Chrome, Firefox, Safari and Edge (light/dark, print preview) is done by a human at release (ADS 10.1 Visual layer).

Validation catalogue: `tests/cli/test_catalogue_invalid.py` runs every `tests/fixtures/invalid/*.yaml` (one per RS 9 code that applies to YAML input).

| AT | Expected result (RS 11) | File(s) | Test functions |
| --- | --- | --- | --- |
| AT-01 | Exit 0; p.json equals scheduling-worked-example.expected.json byte … | `golden/test_golden_plans.py` | `test_at_01_worked_example_plan`, `test_at_01_plan_rt_version` |
| AT-02 | Each rt-bar has data-start, data-end, data-lane, data-color-index e… | `html/test_html_worked_example.py` | `test_at_02_bar_attributes_match_plan`, `test_at_02_plan_matches_expected_schedule` |
| AT-03 | Reporting bar: left: 110.39px; width: 114.76px. Quick win: left: 12… | `html/test_html_worked_example.py` | `test_at_03_bar_geometry`, `test_at_03_all_bar_geometry` |
| AT-04 | Maintenance bar left: 242.00px; width: 476.00px, flag continues, sh… | `html/test_html_worked_example.py` | `test_at_04_ongoing_bar` |
| AT-05 | rt-today with data-date="2027-02-15" at x = 180.00 px | `html/test_html_worked_example.py` | `test_at_05_today_line`, `test_at_05_today_label` |
| AT-06 | Beta lane 1 holds Quick win, Q2 launch, Big bang in that left-to-ri… | `html/test_html_worked_example.py` | `test_at_06_backfill_order`, `test_at_06_lanes_and_teams` |
| AT-07 | Exit 0; Reporting in Alpha lane 3 from 2027-01-01, Big bang in Beta… | `acceptance/test_at_scheduling.py` | `test_at_07_overflow_mode` |
| AT-08 | Exit 3; E061 for Reporting and Big bang; no HTML written | `acceptance/test_at_scheduling.py` | `test_at_08_error_mode` |
| AT-09 | Exit 3, E060 naming the M project | `acceptance/test_at_scheduling.py` | `test_at_09_unschedulable` |
| AT-10 | For every pair in each neighbors list, colours differ; no W007 | `acceptance/test_at_scheduling.py` | `test_at_10_neighbours_have_distinct_colours` |
| AT-11 | Its color_index is 4 whatever its neighbours; neighbours avoid sky | `acceptance/test_at_scheduling.py` | `test_at_11_pinned_colour` |
| AT-12 | Core API and Reporting clipped_left (W002 each); Big bang clipped_r… | `acceptance/test_at_scheduling.py` | `test_at_12_horizon_clipping` |
| AT-13 | Team utilisation: Alpha data-utilization="0.7624" shown as 76 %, Be… | `html/test_html_worked_example.py` | `test_at_13_team_utilisation` |
| AT-14 | Exit 1; E030, E031, E013 all reported, sorted by line, with line an… | `acceptance/test_at_validation.py` | `test_at_14_all_errors_collected`, `test_at_14_diagnostics_sorted` |
| AT-15 | E002 with "did you mean "parallel\_projects"?" | `acceptance/test_at_validation.py` | `test_at_15_unknown_key_suggestion` |
| AT-16 | E032 | `acceptance/test_at_validation.py` | `test_at_16_size_and_ongoing` |
| AT-17 | Exit 1; output file not created; a pre-existing output file unchanged | `cli/test_cli_commands.py` | `test_at_17_strict_writes_nothing` |
| AT-18 | First exit 0 and the file renders with exit 0; second exit 4; with … | `cli/test_cli_commands.py` | `test_at_18_init_twice`, `test_at_18_init_path_and_minimal` |
| AT-19 | HTML on stdout only; summary on stderr | `cli/test_cli_commands.py` | `test_at_19_stdin_to_stdout` |
| AT-20 | JSON array of diagnostics on stdout; no file written | `cli/test_cli_commands.py` | `test_at_20_validate_json`, `test_at_20_validate_text_writes_nothing` |
| AT-21 | Exit 2 with usage hint | `cli/test_cli_commands.py` | `test_at_21_unknown_option` |
| AT-22 | Appears as literal text; no <script element in the output | `html/test_html_output_quality.py` | `test_at_22_script_name_is_literal_text` |
| AT-23 | Text preserved exactly; NO is a string, not false | `html/test_html_output_quality.py` | `test_at_23_polish_and_no_string` |
| AT-24 | SHA-256 of both HTML files equal; no http:, https: or // URL in src… | `html/test_html_output_quality.py` | `test_at_24_deterministic_and_offline` |
| AT-25 | Visual review against section 7: sticky headers, colours, glyphs, l… | `html/test_html_output_quality.py` | `test_at_25_visual_review_structure` |
| AT-26 | Exit 0; p.json equals dependencies-example.expected.json byte for b… | `golden/test_golden_plans.py` | `test_at_26_dependencies_plan` |
| AT-27 | data-delay-reason: Web checkout dependency, Load testing dependency… | `acceptance/test_at_scheduling.py` | `test_at_27_delay_reasons` |
| AT-28 | Design system and Mobile release: data-requested="auto", flag auto_… | `acceptance/test_at_scheduling.py` | `test_at_28_auto_start` |
| AT-29 | Inside the Product card, rt-dep 1→2 and 2→4 exist and 1→7 exists; n… | `html/test_html_dependencies.py` | `test_at_29_connectors`, `test_at_29_external_dependency_glyph`, `test_at_29_tooltips_list_dependencies`, `test_at_29_depends_on_attribute` |
| AT-30 | Anchor 2027-02-01: Design system Web lane 2, 2027-02-01–2027-03-01;… | `acceptance/test_at_scheduling.py` | `test_at_30_from_moves_anchor` |
| AT-31 | Release audit in Ops lane 3 from 2027-03-26, flags delayed (reason … | `acceptance/test_at_scheduling.py` | `test_at_31_overflow_with_dependencies` |
| AT-32 | Exit 1; E034 (with "did you mean"), E035, E036, E037, E023 all repo… | `acceptance/test_at_validation.py` | `test_at_32_dependency_errors` |
| AT-33 | WE: rt-quarter labels 2027-Q1, 2027-Q2; one dotted rt-quarter-line … | `html/test_html_worked_example.py` | `test_at_33_quarters_worked_example`, `test_at_33_quarters_example` |
| AT-34 | One rt-summary; rt-load-cell values equal the table in 7.12 (e.g. A… | `html/test_html_worked_example.py` | `test_at_34_summary_load_cells`, `test_at_34_summary_heading_and_order` |
| AT-35 | Alpha Jan 140 % and Beta Apr 177 % in the over-100 % colour #FCA5A5… | `html/test_html_worked_example.py` | `test_at_35_overflow_summary` |
| AT-36 | "Płatności odroczone (BNPL) pilot" appears exactly, its elements ca… | `html/test_html_dependencies.py` | `test_at_36_polish_text_and_lang`, `test_at_36_lang_on_all_user_text`, `test_at_36_decomposed_dependency_name` |
| AT-37 | Both exit 0; a.html and b.html byte-identical; the first run's summ… | `cli/test_cli_streams.py` | `test_at_37_stdin_equals_file` |
| AT-38 | stdout equals scheduling-worked-example.expected.json (ignoring rt_… | `cli/test_cli_streams.py` | `test_at_38_plan_to_stdout` |
| AT-39 | Both exit 2 without reading input; stdout empty | `cli/test_cli_streams.py` | `test_at_39_two_artifacts_on_stdout` |
| AT-40 | Exit 2, message no input; give a file or pipe data into rt; stdout … | `cli/test_cli_streams.py` | `test_at_40_terminal_stdin` |
| AT-41 | Exit 1; E001 input is empty … reported for <stdin>; stdout empty | `cli/test_cli_streams.py` | `test_at_41_empty_input` |
| AT-42 | Text: stderr lines start with <stdin>:; exit 1. JSON: array on stdo… | `cli/test_cli_streams.py` | `test_at_42_stdin_diagnostics` |
| AT-43 | Exit 1; stdout 0 bytes | `cli/test_cli_streams.py` | `test_at_43_failure_writes_nothing_to_stdout` |
| AT-44 | rt exits 141 (PIPESTATUS[0]); stderr empty | `cli/test_cli_streams.py` | `test_at_44_closed_pipe`, `test_at_44_closed_pipe_shell` |
| AT-45 | stdout bytes equal the -o file bytes; Płatności present as UTF-8; n… | `cli/test_cli_streams.py` | `test_at_45_stdout_bytes_independent_of_locale` |
| AT-46 | Both exit 0; m.html is complete HTML; the schema parses as JSON | `cli/test_cli_streams.py` | `test_at_46_chaining` |
| AT-47 | Exit 0; stdout byte-equal to projects.minimal.expected.yaml; rt val… | `acceptance/test_at_convert.py`, `unit/test_convert_command.py` | `test_at_47_minimal_csv`, `test_at_47_minimal_csv_to_stdout` |
| AT-48 | Exit 0; out.yaml byte-equal to projects.pl.expected.yaml; stderr ha… | `acceptance/test_at_convert.py`, `unit/test_convert_command.py` | `test_at_48_polish_csv_with_base`, `test_at_48_matches_reference_converter`, `test_at_48_worked_example_to_file_with_exact_stderr` |
| AT-49 | Exit 0; plan: Widżety Android in app lane 1 from 2027-03-26, 25 day… | `acceptance/test_at_convert.py` | `test_at_49_convert_piped_into_render` |
| AT-50 | Comma and tab: output equals AT-48 apart from the file name in the … | `acceptance/test_at_convert.py`, `unit/test_convert_command.py` | `test_at_50_other_delimiters`, `test_at_50_cp1250`, `test_at_50_delimiter_override`, `test_at_50_resaved_variants_equal_at_48`, `test_at_50_cp1250_without_encoding_is_e102` |
| AT-51 | Exit 1; stdout empty; codes (a) E103, (b) E030 with a suggestion, (… | `acceptance/test_at_convert.py`, `unit/test_convert_command.py` | `test_at_51_invalid_csvs`, `test_at_51_polish_header_in_message`, `test_at_51_invalid_csvs` |
| AT-52 | Subdomains kanaly-platnosci, merchant, roadmap; teams karty, platno… | `acceptance/test_at_convert.py`, `unit/test_convert_command.py` | `test_at_52_skeleton`, `test_at_52_skeleton` |
| AT-53 | E107; E031; exit 2 (usage) | `acceptance/test_at_convert.py`, `unit/test_convert_command.py` | `test_at_53_skeleton_errors`, `test_at_53_custom_sizes_written`, `test_at_53_e107_e031_and_usage` |
| AT-54 | E105 for every row; every project team: app; the base project first… | `acceptance/test_at_convert.py`, `unit/test_convert_command.py` | `test_at_54_team_resolution_with_base`, `test_at_54_single_team_base`, `test_at_54_team_from_base_option_or_e105` |
| AT-55 | Exit 0; both outputs identical, and equal to projects.minimal.expec… | `acceptance/test_at_convert.py`, `unit/test_convert_command.py` | `test_at_55_stdin_twice`, `test_at_55_stdin_twice` |
| AT-56 | Every bar of a product has the product's data-color-index; plan pro… | `acceptance/test_at_products.py` | `test_at_56_product_bars_share_the_product_colour`, `test_at_56_products_plan_is_golden` |
| AT-57 | That bar is sky (index 4); the product's other bars keep the produc… | `acceptance/test_at_products.py` | `test_at_57_project_pin_wins_over_product_colour` |
| AT-58 | Standalone bars use indices 0–9 only and none shares a colour with … | `acceptance/test_at_products.py` | `test_at_58_standalone_bars_avoid_product_colours` |
| AT-59 | Plans equal the updated expected files: every colour unchanged, pro… | `acceptance/test_at_products.py` | `test_at_59_files_without_products_keep_their_colours`, `test_at_59_colours_equal_the_reference_colours` |
| AT-60 | Exit 1; E038 and E039 with "did you mean", E024, E025, all position… | `acceptance/test_at_products.py` | `test_at_60_product_reference_errors` |
| AT-61 | W013 | `acceptance/test_at_products.py` | `test_at_61_product_without_projects` |
| AT-62 | 32 distinct product colours; W014 for the two products that share | `acceptance/test_at_products.py` | `test_at_62_more_products_than_colours` |
| AT-63 | Legend has one rt-product chip per product in file order; tooltips … | `acceptance/test_at_products.py` | `test_at_63_legend_and_tooltips` |
| AT-64 | product: written as the id (a name resolves too); unknown value → E… | `acceptance/test_at_products.py` | `test_at_64_convert_product_column` |
| AT-65 | The schema accepts products and project.product, and still validate… | `acceptance/test_at_products.py` | `test_at_65_schema_accepts_products` |
| AT-66 | Team values as in RS 7.13; only Cyberbezpieczeństwo flagged (no_qa) | `acceptance/test_at_team_indicators.py` | `test_at_66_team_values_and_flags` |
| AT-67 | team_indicators: all, median, band and source for both indicators | `acceptance/test_at_team_indicators.py` | `test_at_67_roadmap_values` |
| AT-68 | rt-team hooks equal the plan; red no QA; red ▲ / green ▼ chips with no… | `acceptance/test_at_team_indicators.py` | `test_at_68_label_chips_and_hooks` |
| AT-69 | WE values without marks; DE and PE no_capacity; plans equal the exp… | `acceptance/test_at_team_indicators.py` | `test_at_69_other_fixtures` |
| AT-70 | team_norms bands: Karty high, Ops low, Panel merchanta high; bounds… | `acceptance/test_at_team_indicators.py` | `test_at_70_team_norms` |
| AT-71 | Exit 1; E012 at the max, E011, E002 with did you mean | `acceptance/test_at_team_indicators.py` | `test_at_71_invalid_norms` |
| AT-72 | KPI tiles DEV per slot 2.2, DEV per QA 2.6; one rt-composition tabl… | `acceptance/test_at_team_indicators.py` | `test_at_72_summary`, `test_at_72_no_summary_no_table` |
| AT-73 | Same diagnostics as before (no new warnings) | `acceptance/test_at_team_indicators.py` | `test_at_73_no_new_warnings` |
| AT-74 | The schema accepts team_norms and still validates every fixture | `acceptance/test_at_team_indicators.py` | `test_at_74_schema` |
