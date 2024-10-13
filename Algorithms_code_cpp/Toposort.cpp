
const int N=2000;

vector<int> g[N];
int state[N],nodes;//leer nodes en el input como cantidad de nodos 
vi order;
bool cycle=false;

void dfs_topo(int u){
    if(state[u]==1) cycle=true;
    if(state[u]) return;
    state[u]=1;
    for(auto x : g[u]) dfs_topo(x);
    state[u]=2;
    order.pb(u);
}

void toposort(){
    rep(i,1,nodes+1) if(!state[i]) dfs_topo(i);
    reverse(all(order));
    // the toposort will be ar the vector ORDER ready to be procesed 
}
