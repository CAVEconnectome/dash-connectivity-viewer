# Configuration

Environmental variables that need to be set

## Common

### Required

* DEFAULT_DATASTACK : datastack to use for looking up info/creating the CAVE client

* DEFAULT_SERVER_ADDRESS : name of the global server for the CAVEclient

### Optional

There are three categories of optional parameters.

#### If left unset, inferred by info service

* VOXEL_RESOLUTION : voxel resolution to use for the viewer, as three numbers separated by commas with no spaces. Can also be looked up from the info service, which is preferable.

* SYNAPSE_TABLE : Name of the synapse table. Can be inferred from the info service of the datastack.

* NUCLEUS_TABLE : Table name to use for querying nucleus ids, which are stable per-cell ids used for things like counting the number of distinct soma per root id.

#### Set if nucleus table is not all neurons

* SOMA_TABLE_CELL_TYPE : If the soma table has cell type information, this is the value to restrict rows to when assigning cell location. Omit if no filtering is necessary.

* SOMA_CELL_TYPE_COLUMN : Column to use to define cell types when querying the soma table for neurons. Default is `cell_type`.

#### Adapt to schema used for synapse and soma table

* SYN_POSITION_COLUMN : Bound point name in the synapse schema to use for defining synapse position. Default is `ctr_pt`, but this may not exist for all datasets. Note that only the prefix should be provided, not the `_position` suffix.

* SOMA_POSITION_COLUMN : Bound point name in the Nucleus table to use for defining cell location. Default is `pt`. Note that only the prefix should be provided, not the `_position` suffix.

#### Defaults are set for performance

* TARGET_ROOT_ID_PER_CALL : Some parts of the synapse queries are multithreaded (to get number of associated soma), and this parameter sets the root ids per cell. By default 200.

* MAX_DATAFRAME_LENGTH : Limit of dataframe size for automatic table link generation. Default is 8,000.

* MAX_SERVER_DATAFRAME_LENGTH : Length of dataframe before switching over to the link shortener. Default is 20,000.


