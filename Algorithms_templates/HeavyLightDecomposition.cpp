const int N=1e5+10;

int tree[2*N],wyn[N],n,m;
vector<int> g[N];


int query_st(int a,int b){
      a+=n-1,b+=n-1;
      int ans=1e9;
      while(a<=b){
            if(a%2==1) ans=min(ans,tree[a++]);
            if(b%2==0) ans=min(ans,tree[b--]); 
            a/=2,b/=2;
      }
      return ans;
}

void update_st(int val,int idx){ // { index , value }
      idx+=n-1;
      tree[idx]=val;
      for(idx/=2;idx>=1;idx/=2){
            tree[idx]=min(tree[idx<<1],tree[idx<<1|1]);
      }
}

int gid=1,p[N],dep[N],tsz[N],id[N],rt[N];

int dfs_sz(int u,int pai=-1,int d=0){
      p[u]=pai;dep[u]=d;tsz[u]=1;
      for(auto x : g[u]) if(x!=pai){
            tsz[u]+=dfs_sz(x,u,d+1);
      }
      return tsz[u];
}

void dfs_hld(int u,int root=1){
      id[u]=gid++;
      rt[u]=root;
      int w=0,wsz=-1;
      for(auto x : g[u]) if(x!=p[u] and tsz[x]>wsz){
            w=x;
            wsz=tsz[x];
      }
      if(w) dfs_hld(w,root);
      for(auto x: g[u]) if(x!=p[u] and x!=w) dfs_hld(x,x);
}

void update(int node, int val){ // { node for update , value  }
      int idx=id[node];
      update_st(val,idx);
}

int query(int u,int v){
      int ans=1e9;
      while(rt[u]!=rt[v]){
            if(dep[rt[u]]>dep[rt[v]]) swap(u,v);
            ans=min(ans,query_st(id[rt[v]],id[v]));
            v=p[rt[v]];
      }
      int a=id[u],b=id[v];
      if(a>b) swap(a,b);
      ans=min(ans,query_st(a,b));
      return ans;
}

void init_st(void){
      rep(i,1,2*N) tree[i]=1e9;
}

void init_hld(void){
      dfs_sz(1);
      dfs_hld(1);
      init_st();
}
