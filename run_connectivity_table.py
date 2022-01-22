from dash_connectivity_viewer.connectivity_table import create_app

config = {
    "datastack": "fanc_production_mar2021",
    "server_address": "https://global.daf-apis.com",
    "syn_position_column": "pre_pt",
    "nucleus_table": "nuclei_aug2021ver2",
    # "synapse_aggregation_rules": {
    #     "mean_size": {
    #         "column": "size",
    #         "agg": "mean",
    #     },
    #     "net_size": {
    #         "column": "size",
    #         "agg": "sum",
    #     },
    # },
}

if __name__ == "__main__":
    app = create_app(config=config)
    app.run_server(port=8050)
