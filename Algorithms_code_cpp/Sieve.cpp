for(lli x=2;x<=n;x++){
	if(sieve[x]) continue;
	for(int u=2*x;u<=n;u+=x){
		sieve[u]=1;
	}
}
