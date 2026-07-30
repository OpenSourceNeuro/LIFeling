# LIFeling static reconstruction tests

Status: **PASSED**

Tests run: **30**; failures: **0**; errors: **0**.

Execution mode: **in-process unittest runner**.

```text
test_n06_uses_ramped_fixed_soc_thevenin_source (test_cold_start_thevenin.ColdStartTheveninRegression.test_n06_uses_ramped_fixed_soc_thevenin_source) ... ok
test_dynamic_battery_subcircuit_is_present (test_dynamic_battery_ngspice.DynamicBatteryNgspiceRegression.test_dynamic_battery_subcircuit_is_present) ... ok
test_ocv_uses_behavioural_voltage_source (test_dynamic_battery_ngspice.DynamicBatteryNgspiceRegression.test_ocv_uses_behavioural_voltage_source) ... ok
test_cold_start_has_bounded_horizon_and_focused_outputs (test_dynamic_battery_runtime.DynamicBatteryRuntimeRegression.test_cold_start_has_bounded_horizon_and_focused_outputs) ... ok
test_dynamic_battery_uses_linear_controlled_soc_current (test_dynamic_battery_runtime.DynamicBatteryRuntimeRegression.test_dynamic_battery_uses_linear_controlled_soc_current) ... ok
test_all_modelled_ic_package_pin_maps_pass (test_static.LIFelingStaticValidation.test_all_modelled_ic_package_pin_maps_pass) ... ok
test_all_subcircuit_instances_resolve_in_packaged_libraries (test_static.LIFelingStaticValidation.test_all_subcircuit_instances_resolve_in_packaged_libraries) ... ok
test_authoritative_source_lock (test_static.LIFelingStaticValidation.test_authoritative_source_lock) ... ok
test_coverage_has_no_unresolved_reference (test_static.LIFelingStaticValidation.test_coverage_has_no_unresolved_reference) ... ok
test_deck_fingerprint_is_deterministic_for_same_source_lock (test_static.LIFelingStaticValidation.test_deck_fingerprint_is_deterministic_for_same_source_lock) ... ok
test_deck_has_physical_u23_and_no_silent_omission (test_static.LIFelingStaticValidation.test_deck_has_physical_u23_and_no_silent_omission) ... ok
test_dynamic_battery_discharge_reduces_soc (test_static.LIFelingStaticValidation.test_dynamic_battery_discharge_reduces_soc) ... ok
test_generated_deck_includes_ngspice_compatible_mcp_model (test_static.LIFelingStaticValidation.test_generated_deck_includes_ngspice_compatible_mcp_model) ... ok
test_mcp6001_ngspice_copy_normalises_resistor_tc_syntax (test_static.LIFelingStaticValidation.test_mcp6001_ngspice_copy_normalises_resistor_tc_syntax) ... ok
test_megohm_is_not_milliohm (test_static.LIFelingStaticValidation.test_megohm_is_not_milliohm) ... ok
test_official_mcp_model_declaration (test_static.LIFelingStaticValidation.test_official_mcp_model_declaration) ... ok
test_open_drain_comparator_polarity_releases_when_plus_is_higher (test_static.LIFelingStaticValidation.test_open_drain_comparator_polarity_releases_when_plus_is_higher) ... ok
test_peak_window_is_active_high_physical_comparator (test_static.LIFelingStaticValidation.test_peak_window_is_active_high_physical_comparator) ... ok
test_portable_boost_oscillator_uses_ngspice_supported_pulse_source (test_static.LIFelingStaticValidation.test_portable_boost_oscillator_uses_ngspice_supported_pulse_source) ... ok
test_provided_mmbt3904_model_card_is_detected_but_not_claimed_exact (test_static.LIFelingStaticValidation.test_provided_mmbt3904_model_card_is_detected_but_not_claimed_exact) ... ok
test_r96_r97_authoritative_designator (test_static.LIFelingStaticValidation.test_r96_r97_authoritative_designator) ... ok
test_ref3020_dbz_physical_pin_order (test_static.LIFelingStaticValidation.test_ref3020_dbz_physical_pin_order) ... ok
test_rv4_switch_mapping_is_physical (test_static.LIFelingStaticValidation.test_rv4_switch_mapping_is_physical) ... ok
test_schematic_crosscheck_has_no_missing_reference_or_footprint (test_static.LIFelingStaticValidation.test_schematic_crosscheck_has_no_missing_reference_or_footprint) ... ok
test_topology_corrections_have_no_blocking_failure (test_static.LIFelingStaticValidation.test_topology_corrections_have_no_blocking_failure) ... ok
test_tps610995_is_fixed_3v6_variant (test_static.LIFelingStaticValidation.test_tps610995_is_fixed_3v6_variant) ... ok
test_vendor_deck_requires_explicit_adapter_library (test_static.LIFelingStaticValidation.test_vendor_deck_requires_explicit_adapter_library) ... ok
test_vendor_profile_fails_until_ti_wrappers_are_approved (test_static.LIFelingStaticValidation.test_vendor_profile_fails_until_ti_wrappers_are_approved) ... ok
test_power_switch_off_uses_operating_point (test_suite_runtime.SuiteRuntimeRegression.test_power_switch_off_uses_operating_point) ... ok
test_run_deck_has_timeout_and_stale_cleanup (test_suite_runtime.SuiteRuntimeRegression.test_run_deck_has_timeout_and_stale_cleanup) ... ok

----------------------------------------------------------------------
Ran 30 tests in 0.309s

OK
```
