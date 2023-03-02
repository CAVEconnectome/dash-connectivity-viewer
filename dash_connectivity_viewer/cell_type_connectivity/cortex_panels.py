import plotly.graph_objects as go
from plotly.subplots import make_subplots
from .cortex_plots import *


def split_bar_fig(ndat, cell_types_split=[None, None], height=350, width=450):

    bar_e = excitatory_bar_plot(
        ndat,
        ndat.config.ct_conn_cell_type_column,
        cell_types=cell_types_split[0],
    )

    bar_i = inhibitory_bar_plot(
        ndat, ndat.config.ct_conn_cell_type_column, cell_types=cell_types_split[1]
    )

    fig = make_subplots(rows=1, cols=2)
    fig.add_trace(bar_e, row=1, col=1)
    fig.update_yaxes(
        autorange="reversed",
    )

    fig.add_trace(bar_i, row=1, col=2)
    fig.update_yaxes(
        autorange="reversed",
    )

    fig.update_layout(
        autosize=True,
        height=height,
        width=width,
        paper_bgcolor="White",
        template="plotly_white",
        showlegend=False,
        margin=dict(l=20, r=20, t=20, b=20),
    )

    return fig


def single_bar_fig(ndat, cell_types=None, height=350, width=350):

    bar = uniform_bar_plot(
        ndat,
        ndat.config.ct_conn_cell_type_column,
        cell_types=cell_types,
    )

    fig = make_subplots(rows=1, cols=1)
    fig.add_trace(bar, row=1, col=1)
    fig.update_yaxes(
        autorange="reversed",
    )

    fig.update_layout(
        autosize=True,
        height=height,
        width=width,
        paper_bgcolor="White",
        template="plotly_white",
        showlegend=False,
        margin=dict(l=20, r=20, t=20, b=20),
    )

    return fig


def violin_fig(ndat, height=350, width=200):

    fig = go.Figure()

    violin_post = post_violin_plot(ndat)
    violin_pre = pre_violin_plot(ndat)
    fig.add_trace(violin_post)
    fig.add_trace(violin_pre)

    fig.update_layout(
        yaxis_title="Synapse Depth",
        height=height,
        width=width,
        paper_bgcolor="White",
        template="plotly_white",
        showlegend=False,
        margin=dict(l=40, r=20, t=20, b=20),
    )

    fig.update_yaxes(
        tickvals=ndat.config.vis.ticklocs - ndat.config.vis.ticklocs[0],
        ticktext=ndat.config.vis.tick_labels,
        ticklabelposition="outside bottom",
        range=(ndat.config.height_bnds-ndat.config.height_bnds[0]).astype(int)[::-1].tolist(),
        gridcolor="#CCC",
        gridwidth=2,
    )
    return fig

def scatter_fig_df(df, config, color_column, width=350, height=350):
    fig = go.Figure()
    scatter = synapse_soma_scatterplot(df, config, color_column)
    fig.add_traces(scatter)

    fig.update_layout(
        xaxis_title="Soma Depth",
        yaxis_title="Synapse Depth",
        height=height,
        width=width,
        paper_bgcolor="White",
        template="plotly_white",
        showlegend=True,
        margin=dict(l=20, r=20, t=20, b=20),
    )

    fig.update_xaxes(
        tickvals=config.vis.ticklocs,
        ticktext=config.vis.tick_labels,
        ticklabelposition="outside right",
        gridcolor="#CCC",
        gridwidth=2,
        scaleanchor="y",
    )

    fig.update_yaxes(
        tickvals=config.vis.ticklocs,
        ticktext=config.vis.tick_labels,
        ticklabelposition="outside bottom",
        range=config.height_bnds.astype(int)[::-1].tolist(),
        gridcolor="#CCC",
        gridwidth=2,
        scaleanchor="x",
        scaleratio=1,
    )
    return fig


def scatter_fig(ndat, color_column, width=350, height=350):

    fig = go.Figure()
    scatter = synapse_soma_scatterplot(
        ndat,
        ndat.config.synapse_depth_column,
        ndat.config.soma_depth_column,
        color_column,
    )
    fig.add_traces(scatter)

    fig.update_layout(
        xaxis_title="Soma Depth",
        yaxis_title="Synapse Depth",
        height=height,
        width=width,
        paper_bgcolor="White",
        template="plotly_white",
        showlegend=True,
        margin=dict(l=20, r=20, t=20, b=20),
    )

    fig.update_xaxes(
        tickvals=ndat.config.vis.ticklocs,
        ticktext=ndat.config.vis.tick_labels,
        ticklabelposition="outside right",
        gridcolor="#CCC",
        gridwidth=2,
        scaleanchor="y",
    )

    fig.update_yaxes(
        tickvals=ndat.config.vis.ticklocs,
        ticktext=ndat.config.vis.tick_labels,
        ticklabelposition="outside bottom",
        range=ndat.config.height_bnds.astype(int)[::-1].tolist(),
        gridcolor="#CCC",
        gridwidth=2,
        scaleanchor="x",
        scaleratio=1,
    )
    return fig
