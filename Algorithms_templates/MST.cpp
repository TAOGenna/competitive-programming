const int N=1e4;
struct MST{
  int p[N];
  vector<pair<int,int> > g[N]; // here will be the spanning tree {[node] -> (neighboor,weight)}
  void clear(int n){ rep(i,0,n+1) p[i] = i; }
  int find(int i){ return (p[i] == i) ? i : (p[i] = find(p[i])); }
  void join(int i, int j){ p[find(i)] = find(j); }
  void ini(vector<pair<int,ii> > &v,int nodes){
  		clear(nodes);
  		sort(all(v));
  		trav(x,v){
			if(find(x.ss.ff)!=find(x.ss.ss)){
				join(x.ss.ff,x.ss.ss);
				g[x.ss.ff].pb({x.ss.ss,x.ff}),g[x.ss.ss].pb({x.ss.ff,x.ff});
			}
		}
  }
};
