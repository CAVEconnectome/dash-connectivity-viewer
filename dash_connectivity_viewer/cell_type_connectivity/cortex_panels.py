import plotly.graph_objects as go
from plotly.subplots import make_subplots
from .config import ticklocs, height_bnds
from .cortex_plots import *


def split_bar_fig(
    ndat, vis_config, cell_types_split=[None, None], height=350, width=450
):

    bar_e = excitatory_bar_plot(
        ndat,
        ndat.cell_type_column,
        vis_config.e_color,
        cell_types=cell_types_split[0],
    )

    bar_i = inhibitory_bar_plot(
        ndat, ndat.cell_type_column, vis_config.i_color, cell_types=cell_types_split[1]
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


def single_bar_fig(ndat, vis_config, cell_types=None, height=350, width=350):

    bar = uniform_bar_plot(
        ndat,
        ndat.cell_type_column,
        vis_config.u_color,
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


def violin_fig(ndat, vis_config, ticklocs=ticklocs, height=350, width=200):

    fig = go.Figure()

    violin_post = post_violin_plot(ndat, vis_config)
    violin_pre = pre_violin_plot(ndat, vis_config)
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
        tickvals=ticklocs,
        ticktext=["L1", "L2/3", "L4", "L5", "L6", "WM", ""],
        ticklabelposition="outside bottom",
        range=height_bnds.astype(int)[::-1].tolist(),
        gridcolor="#CCC",
        gridwidth=2,
    )
    return fig


def scatter_fig(ndat, vis_config, ticklocs=ticklocs, width=350, height=350):

    fig = go.Figure()
    scatter = synapse_soma_scatterplot(
        ndat,
        ndat.synapse_depth_column,
        ndat.soma_depth_column,
        vis_config,
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
        tickvals=ticklocs,
        ticktext=["L1", "L2/3", "L4", "L5", "L6", "WM", ""],
        ticklabelposition="outside right",
        gridcolor="#CCC",
        gridwidth=2,
        scaleanchor="y",
    )

    fig.update_yaxes(
        tickvals=ticklocs,
        ticktext=["L1", "L2/3", "L4", "L5", "L6", "WM", ""],
        ticklabelposition="outside bottom",
        range=height_bnds.astype(int)[::-1].tolist(),
        gridcolor="#CCC",
        gridwidth=2,
        scaleanchor="x",
        scaleratio=1,
    )
    return fig
