from plotly import colors
import plotly.graph_objects as go
import numpy as np
import pandas as pd

def _violin_plot(syn_df, x_col, y_col, name, side, color, xaxis, yaxis):
    return go.Violin(
        x=syn_df[x_col],
        y=syn_df[y_col],
        side=side,
        scalegroup="syn",
        spanmode='hard',
        name=name,
        points=False,
        line_color=f"rgb{color}",
        fillcolor=f"rgb{color}",
        xaxis=xaxis,
        yaxis=yaxis,
        hoverinfo='text',
        hovertext=f"{len(syn_df)} Syn.",
        # bandwidth=0.2,
    )


def post_violin_plot(
    ndat,
    xaxis=None,
    yaxis=None,
):
    return _violin_plot(
        ndat.syn_all_df().query('direction == "post"'),
        x_col="x",
        y_col=ndat.config.synapse_depth_column,
        name="Post",
        side="negative",
        color=ndat.config.vis.dendrite_color,
        xaxis=xaxis,
        yaxis=yaxis,
    )


def pre_violin_plot(
    ndat,
    xaxis=None,
    yaxis=None,
):
    return _violin_plot(
        ndat.syn_all_df().query('direction == "pre"'),
        x_col="x",
        y_col=ndat.config.synapse_depth_column,
        name="Pre",
        side="positive",
        color=ndat.config.vis.axon_color,
        xaxis=xaxis,
        yaxis=yaxis,
    )

from itertools import cycle
def _colorscheme(n):
    if n <= 10:
        clrs = cycle(colors.qualitative.G10)
    else:
        clrs = cycle(colors.qualitative.Dark24)
    return [next(clrs) for i in range(n)]

def synapse_soma_scatterplot(
    targ_df,
    config,
    color_column,
    xaxis=None,
    yaxis=None,
):

    if color_column is None or color_column == "":
        fake_cell_type_column = 'DummyColumn_'
        while fake_cell_type_column in targ_df.columns:
            fake_cell_type_column += 'a'
        color_column = fake_cell_type_column
        targ_df[color_column] = config.null_cell_type_label
        ctypes = [config.null_cell_type_label]
    else:
        if targ_df[color_column].dtype == 'float64':
            targ_df[color_column] = targ_df[color_column].astype(pd.Int64Dtype())
            ctypes = sorted(list(np.unique(targ_df[color_column].dropna()).astype(str)))
            targ_df[color_column] = targ_df[color_column].astype(str).replace(
                {'<NA>': config.null_cell_type_label}
            )
        else:
            ctypes = sorted(list(np.unique(targ_df[color_column].dropna()).astype(str)))
            targ_df[color_column] = targ_df[color_column].fillna(config.null_cell_type_label).astype(str)
        ctypes = ctypes+[config.null_cell_type_label]

    
    if len(ctypes)>1:
        cmap = _colorscheme(len(ctypes)-1) + ['#333333']
    else:
        cmap = ['#333333']

    alpha_default = {config.null_cell_type_label: 0.2}
    panels = []
    alpha= config.vis.e_opacity
    for ct, clr in zip(ctypes, cmap):
        targ_df_r = targ_df.query(f"{color_column}=='{ct}'")
        panel = go.Scattergl(
            x=targ_df_r[config.soma_depth_column],
            y=targ_df_r[config.synapse_depth_column],
            mode="markers",
            marker=dict(
                color=clr,
                line_width=0,
                size=4,
                opacity=alpha_default.get(ct, alpha),
            ),
            xaxis=xaxis,
            yaxis=yaxis,
            name=ct,
            # hoverinfo='none',
        )
        panels.append(panel)

    return panels

def bar_plot_df(
    targ_df,
    config,
    color_value,
):

    targ_df = targ_df.replace({config.null_cell_type_label: None}).dropna(subset=color_value)
    xtypes = sorted(list(np.unique(targ_df[color_value])))
    clrs = _colorscheme(len(xtypes))
    cnts = targ_df.value_counts(color_value).loc[xtypes]

    bar = go.Bar(
        name=color_value,
        x=xtypes,
        y=cnts,
        text=cnts,
        marker_color=clrs,
    )
    return bar


def bar_data(
    ndat,
    cell_type_column,
    num_syn_column,
):
    targ_df = ndat.partners_out().dropna(subset=[cell_type_column])
    return targ_df.groupby(cell_type_column)[num_syn_column].sum()


def _bar_plot(
    bar_data,
    name,
    color,
):
    return go.Bar(
        name=name,
        x=bar_data.values,
        y=bar_data.index,
        marker_color=f"rgb{color}",
        orientation="h",
    )


def _format_color(color, alpha=None):
    color = tuple(np.floor(255 * np.array(color)).astype(int))
    if alpha is None:
        return color
    else:
        return tuple(list(color) + [alpha])


def _prepare_bar_plot(
    ndat,
    cell_type_column,
    color,
    cell_types,
    valence,
):
    if valence == "u":
        if cell_types is None:
            cell_types = np.unique(
                ndat.property_data(ndat.cell_type_table)[cell_type_column]
            )
        name = "Targets"
    else:
        if valence == "i":
            map_ind = "i"
            name = "I Targets"
        elif valence == "e":
            map_ind = "e"
            name = "E Targets"

        if cell_types is None:
            cell_types = (
                ndat.property_data(ndat.cell_type_table)
                .groupby(ndat.valence_map["column"])
                .agg({cell_type_column: np.unique})
                .loc[ndat.valence_map[map_ind]][cell_type_column]
            )

    bdat = bar_data(ndat, cell_type_column, ndat.config.num_syn_col)

    # Fill in any cell types in the table
    for ct in cell_types:
        if ct not in bdat.index:
            bdat.loc[ct] = 0

    return _bar_plot(
        bdat.sort_index().loc[cell_types],
        name,
        _format_color(color),
    )


def excitatory_bar_plot(
    ndat,
    cell_type_column,
    cell_types=None,
):
    return _prepare_bar_plot(
        ndat, cell_type_column, ndat.config.vis.e_color, cell_types, "e"
    )


def inhibitory_bar_plot(
    ndat,
    cell_type_column,
    cell_types=None,
):
    return _prepare_bar_plot(
        ndat, cell_type_column, ndat.config.vis.i_color, cell_types, "i"
    )


def uniform_bar_plot(
    ndat,
    cell_type_column,
    cell_types=None,
):
    return _prepare_bar_plot(
        ndat, cell_type_column, ndat.config.vis.u_color, cell_types, "u"
    )