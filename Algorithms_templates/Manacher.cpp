struct Manacher{
	vector<char> t;
	vector<int> p;
	void init(string s){
		for(int i=1,j=0;i<=(2*sz(s)+1);i++){
			if(i%2) t.pb('#');
			else t.pb(s[j++]);
		}
		p.resize(sz(t));
		int C = 0, R = -1, rad; 
		for (int i = 0; i < sz(t); ++i) {
		    if (i <= R) rad = min(p[2*C-i], R-i); 
		    else rad=0;
		    while (i+rad < sz(t) && i-rad >= 0 && t[i-rad] == t[i+rad]) rad++;
		    p[i] = rad;
		    if (i + rad - 1 > R) C = i,R = i + rad - 1; 
		}for(auto &x : p) x--;
	}
};
