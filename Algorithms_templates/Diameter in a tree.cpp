struct Diameter{ // need to specify N and initialize everything calling sol.ini(adj_list)
public:
	int p[N],node1=0,node2=0,maxi1=0,diameter=0;
	vector<int> path;
	void ini(vector<int> g[]){
		dfs(1,-1,0,maxi1,node1,false);
		dfs(node1,-1,0,diameter,node2,true);
		p[node1]=-1;
		for (int v = node2; v != -1; v = p[v]) path.push_back(v);
	} 
	void dfs(int u,int parent,int dis,int &maxi,int &ans,bool mode){
		if(maxi<dis) maxi=dis,ans=u;
		for(auto x : g[u]) if(x!=parent){
			if(mode) p[x]=u;
			dfs(x,u,dis+1,maxi,ans,mode);
		}
	}
}sol;
