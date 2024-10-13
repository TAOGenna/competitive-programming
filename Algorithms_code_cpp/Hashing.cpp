lli h[N],p[N];
lli B=999999937,A=1000000007;
void hashing(string &s){
	h[0]=s[0];
	p[0]=1;
	for(int i=1;i<s.size();i++){
		h[i]=(h[i-1]*A+s[i])%B;
		p[i]=(p[i-1]*A)%B;
	}
}
long long int ash(int a,int b){
	//a--,b--; // assuming a and b as 1 indexed
	if(a==0) return h[b]; 
	return (h[b]-h[a-1]*p[b-a+1]+B*B)%B;
}
