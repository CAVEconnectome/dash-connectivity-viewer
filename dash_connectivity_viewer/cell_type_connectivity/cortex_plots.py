from plotly import colors
import plotly.graph_objects as go
import numpy as np


def _violin_plot(syn_df, x_col, y_col, name, side, color, xaxis, yaxis):
    return go.Violin(
        x=syn_df[x_col],
        y=syn_df[y_col],
        side=side,
        scalegroup="syn",
        name=name,
        points=False,
        line_color=f"rgb{color}",
        fillcolor=f"rgb{color}",
        xaxis=xaxis,
        yaxis=yaxis,
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

def _colorscheme(n):
    if n <= 10:
        return colors.qualitative.G10
    else:
        return colors.qualitative.Dark24

def synapse_soma_scatterplot(
    targ_df,
    config,
    color_column,
    xaxis=None,
    yaxis=None,
):

    null_type = config.null_cell_type_label
    if color_column is None:
        fake_cell_type_column = 'HereIsADummyColumn_'
        while fake_cell_type_column in targ_df.columns:
            fake_cell_type_column += 'a'
        targ_df[fake_cell_type_column] = null_type
        color_column = fake_cell_type_column

    ctypes = list(np.unique(targ_df[color_column].dropna()))
    targ_df[color_column] = targ_df[color_column].fillna(null_type)
    ctypes = ctypes+[null_type]

    cmap = _colorscheme(len(ctypes))
    cmap_default = {null_type: 'rgb(0.4, 0.4, 0.5)'}
    alpha_default = {null_type: 0.3}
    panels = []
    alpha= config.vis.e_opacity
    
    for ct, clr in zip(ctypes, cmap):
        targ_df_r = targ_df.query(f"{color_column}=='{ct}'")
        panel = go.Scattergl(
            x=targ_df_r[config.soma_depth_column],
            y=targ_df_r[config.synapse_depth_column],
            mode="markers",
            marker=dict(
                color=cmap_default.get(ct, clr),
                line_width=0,
                size=4,
                opacity=alpha_default.get(ct, alpha),
            ),
            xaxis=xaxis,
            yaxis=yaxis,
            name=ct,
            hoverinfo='none',
        )
        panels.append(panel)

    return panels

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