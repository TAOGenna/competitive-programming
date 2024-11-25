
const int N=1e5+10;
vector <int> g[N], gr[N]; // g is my usual graph adj list
bool used[N];
vector<int> order, component; // order->toposort   componenet->temporal list of SCC that I can process 

void dfs1 (int v) {
    used[v] = true;
    for(auto x : g[v]) if(!used[x]) dfs1(x);
    order.pb(v);
}

void dfs2 (int v) {
    used[v] = true;
    component.push_back (v);
    for(auto x : gr[v]) if(!used[x]) dfs2(x);
}
int main() {
    int n,m; cin>>n>>m; // n->#nodes  m->#edges
    rep(i,0,m) {
        int a,b;
        cin>>a>>b;
        g[a].push_back (b);
        gr[b].push_back (a);
    }
    rep(i,1,n+1) used[i]=false;
    rep(i,1,n+1) if (!used[i]) dfs1 (i);
    rep(i,0,n+1) used[i]=false;
    rep(i,1,n+1){
        int v = order[n-i];
        if (!used[v]) {
            dfs2 (v);
          	cout<<"... printing next component ..."<<endl;
            for(auto x : component) cout<<x<<" ";cout<<endl<<endl;
            component.clear();
        }
    }
    return 0;
}
