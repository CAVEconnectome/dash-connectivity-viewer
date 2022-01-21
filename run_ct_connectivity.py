from dash_connectivity_viewer.cell_type_connectivity import create_app

# config = {
#     "cell_type_dropdown_options": [
#         {
#             "label": "All Soma Prediction",
#             "value": "allen_soma_coarse_cell_class_model_v1",
#         },
#         {
#             "label": "Column Census",
#             "value": "allen_v1_column_types_slanted",
#         },
#         {
#             "label": "Column Thalamic Axons",
#             "value": "allen_v1_column_thalamic",
#         },
#         {
#             "label": "Column Basket Subtypes",
#             "value": "allen_column_basket_molecular",
#         },
#     ],
#     "datastack": "minnie65_phase3_v1",
#     "server_address": "https://global.daf-apis.com",
#     "syn_position_column": "ctr_pt",
#     "synapse_aggregation_rules": {
#         "mean_size": {
#             "column": "size",
#             "agg": "mean",
#         },
#         "net_size": {
#             "column": "size",
#             "agg": "sum",
#         },
#     },
#     "cell_type_column_schema_lookup": {
#         "cell_type_local": "cell_type",
#     },
#     "omit_cell_type_tables": ["nucleus_neuron_svm"],
#     "valence_map": {
#         "allen_v1_column_types_slanted": {
#             "column": "classification_system",
#             "e": "aibs_coarse_excitatory",
#             "i": "aibs_coarse_inhibitory",
#         },
#         "allen_soma_coarse_cell_class_model_v1": {
#             "column": "classification_system",
#             "e": "aibs_coarse_excitatory",
#             "i": "aibs_coarse_inhibitory",
#         },
#     },
#     "default_cell_type_option": "allen_soma_coarse_cell_class_model_v1",
# }
config = {
    "datastack": "flywire_fafb_production",
    "server_address": "https://global.daf-apis.com",
    "syn_position_column": "pre_pt",
    "cell_type_column_schema_lookup": {
        "cell_type_local": "cell_type",
    },
    "ct_conn_show_depth_plots": False,
}
if __name__ == "__main__":
    app = create_app(config=config)
    app.run_server(port=8051, debug=True)
