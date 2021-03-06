import numpy as np
import warnings
import tasklogger

from . import base
from . import graphs


def Graph(data,
          n_pca=None,
          sample_idx=None,
          adaptive_k='sqrt',
          precomputed=None,
          knn=5,
          decay=10,
          distance='euclidean',
          thresh=1e-4,
          kernel_symm='+',
          gamma=None,
          n_landmark=None,
          n_svd=100,
          beta=1,
          n_jobs=-1,
          verbose=False,
          random_state=None,
          graphtype='auto',
          use_pygsp=False,
          initialize=True,
          **kwargs):
    """Create a graph built on data.

    Automatically selects the appropriate DataGraph subclass based on
    chosen parameters.
    Selection criteria:
    - if `graphtype` is given, this will be respected
    - otherwise:
    -- if `sample_idx` is given, an MNNGraph will be created
    -- if `precomputed` is not given, and either `decay` is `None` or `thresh`
    is given, a kNNGraph will be created
    - otherwise, a TraditionalGraph will be created.

    Incompatibilities:
    - MNNGraph and kNNGraph cannot be precomputed
    - kNNGraph and TraditionalGraph do not accept sample indices

    Parameters
    ----------
    data : array-like, shape=[n_samples,n_features]
        accepted types: `numpy.ndarray`, `scipy.sparse.spmatrix`.
        TODO: accept pandas dataframes

    n_pca : `int` or `None`, optional (default: `None`)
        number of PC dimensions to retain for graph building.
        If `None`, uses the original data.
        Note: if data is sparse, uses SVD instead of PCA
        TODO: should we subtract and store the mean?

    knn : `int`, optional (default: 5)
        Number of nearest neighbors (including self) to use to build the graph

    decay : `int` or `None`, optional (default: 10)
        Rate of alpha decay to use. If `None`, alpha decay is not used.

    distance : `str`, optional (default: `'euclidean'`)
        Any metric from `scipy.spatial.distance` can be used
        distance metric for building kNN graph.
        TODO: actually sklearn.neighbors has even more choices

    thresh : `float`, optional (default: `1e-4`)
        Threshold above which to calculate alpha decay kernel.
        All affinities below `thresh` will be set to zero in order to save
        on time and memory constraints.

    kernel_symm : string, optional (default: '+')
        Defines method of MNN symmetrization.
        '+'  : additive
        '*'  : multiplicative
        'gamma' : min-max
        'none' : no symmetrization

    gamma: float (default: None)
        Min-max symmetrization constant or matrix. Only used if kernel_symm='gamma'.
        K = `gamma * min(K, K.T) + (1 - gamma) * max(K, K.T)`

    precomputed : {'distance', 'affinity', 'adjacency', `None`}, optional (default: `None`)
        If the graph is precomputed, this variable denotes which graph
        matrix is provided as `data`.
        Only one of `precomputed` and `n_pca` can be set.

    beta: float, optional(default: 1)
        Multiply within - batch connections by(1 - beta)

    sample_idx: array-like
        Batch index for MNN kernel

    adaptive_k : `{'min', 'mean', 'sqrt', 'none'}` (default: 'sqrt')
        Weights MNN kernel adaptively using the number of cells in
        each sample according to the selected method.

    n_landmark : `int`, optional (default: 2000)
        number of landmarks to use

    n_svd : `int`, optional (default: 100)
        number of SVD components to use for spectral clustering

    random_state : `int` or `None`, optional (default: `None`)
        Random state for random PCA

    verbose : `bool`, optional (default: `True`)
        Verbosity.
        TODO: should this be an integer instead to allow multiple
        levels of verbosity?

    n_jobs : `int`, optional (default : 1)
        The number of jobs to use for the computation.
        If -1 all CPUs are used. If 1 is given, no parallel computing code is
        used at all, which is useful for debugging.
        For n_jobs below -1, (n_cpus + 1 + n_jobs) are used. Thus for
        n_jobs = -2, all CPUs but one are used

    graphtype : {'exact', 'knn', 'mnn', 'auto'} (Default: 'auto')
        Manually selects graph type. Only recommended for expert users

    use_pygsp : `bool` (Default: `False`)
        If true, inherits from `pygsp.graphs.Graph`.

    initialize : `bool` (Default: `True`)
        If True, initialize the kernel matrix on instantiation

    **kwargs : extra arguments for `pygsp.graphs.Graph`

    Returns
    -------
    G : `DataGraph`

    Raises
    ------
    ValueError : if selected parameters are incompatible.
    """
    tasklogger.set_level(verbose)
    if sample_idx is not None and len(np.unique(sample_idx)) == 1:
        warnings.warn("Only one unique sample. "
                      "Not using MNNGraph")
        sample_idx = None
        if graphtype == 'mnn':
            graphtype = 'auto'
    if graphtype == 'auto':
        # automatic graph selection
        if sample_idx is not None:
            # only mnn does batch correction
            graphtype = "mnn"
        elif precomputed is None and (decay is None or thresh > 0):
            # precomputed requires exact graph
            # no decay or threshold decay require knngraph
            graphtype = "knn"
        else:
            graphtype = "exact"

    # set base graph type
    if graphtype == "knn":
        basegraph = graphs.kNNGraph
        if precomputed is not None:
            raise ValueError("kNNGraph does not support precomputed "
                             "values. Use `graphtype='exact'` or "
                             "`precomputed=None`")
        if sample_idx is not None:
            raise ValueError("kNNGraph does not support batch "
                             "correction. Use `graphtype='mnn'` or "
                             "`sample_idx=None`")

    elif graphtype == "mnn":
        basegraph = graphs.MNNGraph
        if precomputed is not None:
            raise ValueError("MNNGraph does not support precomputed "
                             "values. Use `graphtype='exact'` and "
                             "`sample_idx=None` or `precomputed=None`")
    elif graphtype == "exact":
        basegraph = graphs.TraditionalGraph
        if sample_idx is not None:
            raise ValueError("TraditionalGraph does not support batch "
                             "correction. Use `graphtype='mnn'` or "
                             "`sample_idx=None`")
    else:
        raise ValueError("graphtype '{}' not recognized. Choose from "
                         "['knn', 'mnn', 'exact', 'auto']")

    # set add landmarks if necessary
    parent_classes = [basegraph]
    msg = "Building {} graph".format(graphtype)
    if n_landmark is not None:
        parent_classes.append(graphs.LandmarkGraph)
        msg = msg + " with landmarks"
    if use_pygsp:
        parent_classes.append(base.PyGSPGraph)
        if len(parent_classes) > 2:
            msg = msg + " with PyGSP inheritance"
        else:
            msg = msg + " and PyGSP inheritance"

    tasklogger.log_debug(msg)

    class_names = [p.__name__.replace("Graph", "") for p in parent_classes]
    try:
        Graph = eval("graphs." + "".join(class_names) + "Graph")
    except NameError:
        raise RuntimeError("unknown graph classes {}".format(parent_classes))

    params = kwargs
    for parent_class in parent_classes:
        for param in parent_class._get_param_names():
            try:
                params[param] = eval(param)
            except NameError:
                # keyword argument not specified above - no problem
                pass

    # build graph and return
    tasklogger.log_debug("Initializing {} with arguments {}".format(
        parent_classes,
        ", ".join(["{}='{}'".format(key, value)
                   for key, value in params.items()
                   if key != "data"])))
    return Graph(**params)
