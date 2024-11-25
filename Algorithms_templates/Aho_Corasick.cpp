
const int N=1e5+10,M=60,a='A';
struct ElMancoCorasick{
	int g[N][M],f[N],out[N];
	int nodes=0;
	bool pattern[N],check[N];
	map<int,int> inde;

	void inst(string s,int ind){
		int node=0;
		for(auto x : s){
			int loc=x-a;
			if(g[node][loc]!=-1) node=g[node][loc];
			else node=g[node][loc]=++nodes;
		}
		pattern[node]=true;
		inde[node]=ind;
	}

	void build(void){
		queue<int> q;
		rep(i,0,M) if(g[0][i]){ q.push(g[0][i]); f[i]=0; };
		while(!q.empty()){
			auto r=q.front();q.pop();
			rep(i,0,M){
				if(g[r][i]==-1) continue;
				auto u=g[r][i];
				q.push(u);
				auto v=f[r];
				while(g[v][i]==-1) v=f[v];
				f[u]=g[v][i];
				// out(u):=out(u) U out(f(u))
				// current node = u ---- suffix link node = f[u]
				if(pattern[f[u]]) out[u]=f[u];
				else out[u]=out[f[u]];
			}
		}
	}
}go;

int main(){
	// the text which will be analized is called "tx"
	// setting up g[][] = {-1}
	// insert all the patterns into the trie
	// rep(i,0,M) if(go.g[0][i]==-1) go.g[0][i]=0; // base case
	//go.build();
	...
	...
	
	// here we process all subtrings which make match in the text
	for(int i=0;i<sz(tx);i++){
		while(go.g[q][tx[i]-a]==-1) q=go.f[q];
		q=go.g[q][tx[i]-a];
		int aux=q;
		if(go.out[aux] or go.pattern[aux]){
			// here's where we find all patterns 
			if(go.pattern[aux]){
				answer.insert(pat[go.inde[aux]]); // string pat[go.inde[aux]] is a subtring of tx 
			}
			while(go.out[aux]){
				answer.insert(pat[go.inde[go.out[aux]]]); // string pat[go.inde[go.out[aux]]] is a subtring of tx 
				aux=go.out[aux];
			}
		}
	}
	
	...
	...
	
	
	return 0;
}
