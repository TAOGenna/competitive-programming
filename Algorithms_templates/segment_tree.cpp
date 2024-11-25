
int n,h;

/////////////////// query normalito de updates y queries de abajo hacia arriba ////////////

//ejemplo de segment tree
//query de maximo en un rango
//update de un elemento

int query(int a,int b){
	a+=n-1,b+=n-1;
	int ans=0;
	while(a<=b){
		if(a%2==1) ans=max(ans,tree[a++]);
		if(b%2==0) ans=max(ans,tree[b--]); 
		a/=2,b/=2;
	}
	return ans;
}

void update(int x,int k){
	k+=n-1;
	tree[k]=x;
	for(k/=2;k>=1;k/=2){
		tree[k]=max(tree[k<<1],tree[k<<1|1]);
	}
}

////////////////////////////////////////////////////////////////////////////////////

/////////////////////////	query hecha de arriba hacia abajo		//////////////////////////////////////////////////

int query(int a,int b,int nodo=1,int l=1,int r=n){
	if(l>=a and  r<=b) return tree[nodo];
	else if(l>b or r<a) return 0;
	int mid=(l+r)/2;
	return max(query(a,b,nodo<<1,l,mid),query(a,b,nodo<<1|1,mid+1,r));
}

void update(int x,int k){
	k+=n-1;
	tree[k]=x;
	for(k/=2;k>=1;k/=2){
		tree[k]=max(tree[k<<1],tree[k<<1|1]);
	}
}



///////////////////////////////// ejemplito clasico de Lazy Progagation	////////////////////////////////////////////////////
// update :  incrementar cada elemento entre [a,b] por x
// query : calcular la suma de los valores entre [a,b]

pair<int,int> tree[2*N];
int szt[2*N];

void go_update(int a,int b,int value,int node=1,int l=1,int r=n){
	if(l>=a and r<=b){
		tree[node].second+=value;
		return;
	}else if(l>b or r<a) return;
	int mid=(l+r)/2;
	go_update(a,b,value,node<<1,l,mid);
	go_update(a,b,value,node<<1|1,mid+1,r);
}

void update_branch(int p){
	p+=n-1;
	tree[p].first=tree[p].first+tree[p].second;	tree[p].second=0;
	for(p/=2;p>=1;p/=2){
		tree[p].first=tree[p<<1].first+tree[p<<1|1].first+tree[p<<1].second*szt[p<<1]+tree[p<<1|1].second*szt[p<<1|1];
	}	
}

void update(int a,int b,int val){
	go_update(a,b,val);
	update_branch(a);
	update_branch(b);
}

int go_query(int a,int b,int node=1,int l=1,int r=n){
	if(l>=a and r<=b){
		return tree[node].first;
	}else if(l>b or r<a) return 0;
	int mid=(l+r)/2;
	return go_query(a,b,node<<1,l,mid)+go_query(a,b,node<<1|1,mid+1,r);
}

void push(int p){
	h = sizeof(int) * 8 - __builtin_clz(n);
	for(int i=h;i>=1;i--){
		int node=p>>i;
		tree[node].first+=tree[node].second*szt[node];

		if(p<n) tree[node<<1].second+=tree[node].second;
		if(p<n) tree[node<<1|1].second+=tree[node].second;

		tree[node].second=0;
	}
}

int query(int a,int b){
	push(a);
	push(b);
	return go_query(a,b);
}
////////////////////////////////////////////////////////////////////////////////////////////

int main(){

	cin>>n;
	jael(n);

	rep(i,0,n){
		int foo; cin>>foo;
		tree[i+n].first=foo;
		szt[i+n]=1;
	}

	for(int i=n-1;i>=1;i--){
		tree[i].first=tree[i<<1].first+tree[i<<1|1].first;
		szt[i]+=szt[i<<1]+szt[i<<1|1];
	}

	int q; cin>>q;
	while(q--){
		int tipo; cin>>tipo;
		if(tipo==1){
			// caso de query 
			int a,b; cin>>a>>b;
			cout<<query(a,b)<<endl;
		}else{
			//caso de update
			int a,b,ind; cin>>a>>b>>ind;
			update(a,b,ind);
		}
	}


	return 0;
}
