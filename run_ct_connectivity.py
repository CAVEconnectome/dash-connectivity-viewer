from dash_connectivity_viewer.cell_type_connectivity import create_app


if __name__ == "__main__":
    app = create_app()
    app.run_server(port=8050)
