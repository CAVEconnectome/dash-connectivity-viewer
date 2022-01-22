# Configuration

Configuration variables that need to be set for proper functioning. All items are keys in a dict passed to `create_app`.

## Required

These values are required for all tools.

* `default_datastack` : datastack to use for looking up info/creating the CAVE client

* `default_server_address` : name of the global server for the CAVEclient, same as passed to CAVEclient.

## Common across most tools

All remaining values are, in general, optional. However, variations in schema (particularly synapse schema) might demand some settings to make it work.

#### If left unset, inferred by info service

* `voxel_resolution` : voxel resolution to use for the viewer, as three numbers separated by commas with no spaces. Can also be looked up from the info service, which is preferable.

* `synapse_table` : Name of the synapse table. Can be inferred from the info service of the datastack.

* `nucleus_table` : Table name to use for querying nucleus ids, which are stable per-cell ids used for things like counting the number of distinct soma per root id.

#### Set if nucleus table is not all neurons

* `soma_table_cell_type` : If the soma table has cell type information, this is the value to restrict rows to when assigning cell location. Omit if no filtering is necessary.

* `soma_cell_type_column` : Column to use to define cell types when querying the soma table for neurons. Default is `cell_type`.

The net result of these two items is that the dataframe is filtered according to `df.query({soma_cell_type_column}=="{soma_table_cell_type}")`.

#### Adapt to schema used for synapse and soma table

* `syn_position_column` : Bound point name in the synapse schema to use for defining synapse position. Default is `ctr_pt`, but this may not exist for all datasets. Note that only the prefix should be provided, not the `_position` suffix.

* `synapse_aggregation_rules` : Defines how to aggregate the properties of individual synapses when displaying connections with synaptic partners. This item should be a dictionary whose keys are new column names and whose values are dictionaries with two values:

  * `column` : Name of column to aggregate.

  * `agg`: Aggregation function to apply.

* `soma_position_column` : Bound point name in the Nucleus table to use for defining cell location. Default is `pt`. Note that only the prefix should be provided, not the `_position` suffix.

#### Defaults that are set for performance

* `target_root_id_per_call` : Some parts of the synapse queries are multithreaded (to get number of associated soma), and this parameter sets the root ids per cell. By default 200.

* `max_dataframe_length` : Limit of dataframe size for automatic table link generation. Default is 8,000.

* `max_server_dataframe_length` : Length of dataframe before switching over to the link shortener. Default is 20,000.

---

## Cell Type Table

### Optional variables

* `ct_cell_type_schema` : List of items specifying the cell type schema to use. Currently, only schema that include the information in `cell_type_local` schema are supported, hence it is the default, but the plan is for this to generalize.

* `ct_schema_soma_pt` : Name of the bound point indicating the soma locations in the cell type schema. Default is `pt`.

* `omit_cell_type_tables` : If provided, a list of cell type tables to not include in the cell type dropdown menu.

* `cell_type_dropdown_options` : If provided, renames specified columns. This should be a list of dictionaries with two keys:
  
  * `name`: Table name in database.

  * `label` : Desired label for the table in the dropdown.

---
## Cell Type Connectivity

Each item here is a key in a dictionary, with values described. All are lower case with underscores.


* `cell_type_dropdown_options` : If provided, renames specified columns. This should be a list of dictionaries with two keys:
  
  * `name`: Table name in database.

  * `label` : Desired label for the table in the dropdown.

  
* `omit_cell_type_tables` : If provided, a list of cell type tables to not include in the cell type dropdown menu.

* `valence_map`: This item describes how to convert table data into excitatory/inhibitory valence information, specific to each table. It is a dict with keys being annotation table names and values:
  
  * `column` : Name of column that gives valence information.

  * `e` : Value in column associated with excitatory neurons.

  * `i` : Value in column associated with inhibitory neurons.

* `cell_type_column_schema_lookup` : This item is a dict mapping schema names as keys to the column name to use to indicate cell type in the table. This is how it will work to use additional schema for the cell typing, but this feature is not yet tested and probably won't work out of the box. At the moment, the value should be:

        ```python
        {
            "cell_type_local": "cell_type",
        },
        ```

* `default_cell_type_dropdown` : The value is the table name to select by default when loading the page fresh.

* `ct_conn_cell_type_column` : Defines the name of the cell type column to be displayed, by default `cell_type`.

* `ct_conn_soma_depth_column` : Defines the name of the soma depth column to be displayed, by default `soma_depth`.

* `ct_conn_is_inhibitory_column` : Defines the name of the column displaying a boolean value for a cell being inhibitory, by default `is_inhibitory`.

* `ct_conn_show_plots` : If `True`, makes bar and synapse plots.

* `ct_conn_show_depth_plots` : If `True` (default), make plots using soma depth.

* `ct_conn_cell_type_schema` : Comma-separated list of schema names to allow in the cell types table. This is temporary until additional schema are tested and working, at which point it will be set by the config (see above).

* `ct_conn_dendrite_color` : Comma-separated floating point rgb values to use for the postsynaptic color in the violin plot.

* `ct_conn_axon_color` : Comma-separated floating point rgb values to use for the presynaptic color in the violin plot.

* `ct_conn_e_palette`/`ct_conn_e_palette`/`ct_conn_u_palette` : Seaborn color palette to use to set a range of colors for excitatory/inhibitory/unknown target cells. By default, `RdPu`, `Greens`, and `Greys`.

* `ct_conn_palette_base` : Number between 0 and 8 that sets which item in the palette to draw the main color from. By default, 6.

