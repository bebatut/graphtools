from load_tests import (
    graphtools,
    np,
    sp,
    pygsp,
    nose2,
    data,
    datasets,
    build_graph,
    assert_raises,
    warns,
    raises,
    squareform,
    pdist,
    PCA,
    TruncatedSVD,
)


#####################################################
# Check parameters
#####################################################


@raises(ValueError)
def test_build_knn_with_exact_alpha():
    build_graph(data, graphtype='knn', decay=10, thresh=0)


@raises(ValueError)
def test_build_knn_with_precomputed():
    build_graph(data, n_pca=None, graphtype='knn', precomputed='distance')


@raises(ValueError)
def test_build_knn_with_sample_idx():
    build_graph(data, graphtype='knn', sample_idx=np.arange(len(data)))


@warns(RuntimeWarning)
def test_duplicate_data():
    build_graph(np.vstack([data, data[:10]]),
                n_pca=20,
                decay=10,
                thresh=1e-4)


#####################################################
# Check kernel
#####################################################


def test_knn_graph():
    k = 3
    n_pca = 20
    pca = PCA(n_pca, svd_solver='randomized', random_state=42).fit(data)
    data_nu = pca.transform(data)
    pdx = squareform(pdist(data_nu, metric='euclidean'))
    knn_dist = np.partition(pdx, k, axis=1)[:, :k]
    epsilon = np.max(knn_dist, axis=1)
    K = np.empty_like(pdx)
    for i in range(len(pdx)):
        K[i, pdx[i, :] <= epsilon[i]] = 1
        K[i, pdx[i, :] > epsilon[i]] = 0

    K = K + K.T
    W = np.divide(K, 2)
    np.fill_diagonal(W, 0)
    G = pygsp.graphs.Graph(W)
    G2 = build_graph(data, n_pca=n_pca,
                     decay=None, knn=k, random_state=42,
                     use_pygsp=True)
    assert(G.N == G2.N)
    assert(np.all(G.d == G2.d))
    assert((G.W != G2.W).nnz == 0)
    assert((G2.W != G.W).sum() == 0)
    assert(isinstance(G2, graphtools.graphs.kNNGraph))


def test_knn_graph_sparse():
    k = 3
    n_pca = 20
    pca = TruncatedSVD(n_pca, random_state=42).fit(data)
    data_nu = pca.transform(data)
    pdx = squareform(pdist(data_nu, metric='euclidean'))
    knn_dist = np.partition(pdx, k, axis=1)[:, :k]
    epsilon = np.max(knn_dist, axis=1)
    K = np.empty_like(pdx)
    for i in range(len(pdx)):
        K[i, pdx[i, :] <= epsilon[i]] = 1
        K[i, pdx[i, :] > epsilon[i]] = 0

    K = K + K.T
    W = np.divide(K, 2)
    np.fill_diagonal(W, 0)
    G = pygsp.graphs.Graph(W)
    G2 = build_graph(sp.coo_matrix(data), n_pca=n_pca,
                     decay=None, knn=k, random_state=42,
                     use_pygsp=True)
    assert(G.N == G2.N)
    np.testing.assert_allclose(G2.W.toarray(), G.W.toarray())
    assert(isinstance(G2, graphtools.graphs.kNNGraph))


def test_sparse_alpha_knn_graph():
    data = datasets.make_swiss_roll()[0]
    k = 5
    a = 0.45
    thresh = 0.01
    pdx = squareform(pdist(data, metric='euclidean'))
    knn_dist = np.partition(pdx, k, axis=1)[:, :k]
    epsilon = np.max(knn_dist, axis=1)
    pdx = (pdx.T / epsilon).T
    K = np.exp(-1 * pdx**a)
    K = K + K.T
    W = np.divide(K, 2)
    np.fill_diagonal(W, 0)
    G = pygsp.graphs.Graph(W)
    G2 = build_graph(data, n_pca=None,  # n_pca,
                     decay=a, knn=k, thresh=thresh,
                     random_state=42, use_pygsp=True)
    assert(np.abs(G.W - G2.W).max() < thresh)
    assert(G.N == G2.N)
    assert(isinstance(G2, graphtools.graphs.kNNGraph))


@warns(UserWarning)
def test_knn_graph_sparse_no_pca():
    build_graph(sp.coo_matrix(data), n_pca=None,  # n_pca,
                decay=10, knn=3, thresh=1e-4,
                random_state=42, use_pygsp=True)


#####################################################
# Check interpolation
#####################################################


def test_build_dense_knn_kernel_to_data():
    G = build_graph(data, decay=None)
    n = G.data.shape[0]
    K = G.build_kernel_to_data(data[:n // 2, :])
    assert(K.shape == (n // 2, n))
    K = G.build_kernel_to_data(G.data)
    assert(np.sum(G.kernel != (K + K.T) / 2) == 0)
    K = G.build_kernel_to_data(G.data_nu)
    assert(np.sum(G.kernel != (K + K.T) / 2) == 0)


def test_build_sparse_knn_kernel_to_data():
    G = build_graph(data, decay=None, sparse=True)
    n = G.data.shape[0]
    K = G.build_kernel_to_data(data[:n // 2, :])
    assert(K.shape == (n // 2, n))
    K = G.build_kernel_to_data(G.data)
    assert(np.sum(G.kernel != (K + K.T) / 2) == 0)
    K = G.build_kernel_to_data(G.data_nu)
    assert(np.sum(G.kernel != (K + K.T) / 2) == 0)


def test_knn_interpolate():
    G = build_graph(data, decay=None)
    assert_raises(ValueError, G.interpolate, data)
    pca_data = PCA(2).fit_transform(data)
    transitions = G.extend_to_data(data)
    assert(np.all(G.interpolate(pca_data, Y=data) ==
                  G.interpolate(pca_data, transitions=transitions)))


####################
# Test API
####################


def test_verbose():
    print()
    print("Verbose test: kNN")
    build_graph(data, decay=None, verbose=True)


def test_set_params():
    G = build_graph(data, decay=None)
    assert G.get_params() == {
        'n_pca': 20,
        'random_state': 42,
        'kernel_symm': '+',
        'gamma': None,
        'knn': 3,
        'decay': None,
        'distance': 'euclidean',
        'thresh': 0,
        'n_jobs': -1,
        'verbose': 0
    }
    G.set_params(n_jobs=4)
    assert G.n_jobs == 4
    assert G.knn_tree.n_jobs == 4
    G.set_params(random_state=13)
    assert G.random_state == 13
    G.set_params(verbose=2)
    assert G.verbose == 2
    G.set_params(verbose=0)
    assert_raises(ValueError, G.set_params, knn=15)
    assert_raises(ValueError, G.set_params, decay=10)
    assert_raises(ValueError, G.set_params, distance='manhattan')
    assert_raises(ValueError, G.set_params, thresh=1e-3)
    assert_raises(ValueError, G.set_params, gamma=0.99)
    assert_raises(ValueError, G.set_params, kernel_symm='*')
    G.set_params(knn=G.knn,
                 decay=G.decay,
                 thresh=G.thresh,
                 distance=G.distance,
                 gamma=G.gamma,
                 kernel_symm=G.kernel_symm)
