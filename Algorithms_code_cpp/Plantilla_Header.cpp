#pragma GCC optimize ("Ofast")
#pragma GCC target ("avx,avx2")
#pragma GCC optimize ("trapv")


#include <bits/stdc++.h>
using namespace std;

#define fastio ios_base::sync_with_stdio(0); cin.tie(0); cin.exceptions(cin.failbit);
#define rep(i, a, b) for(lli i = a; i < (b); ++i)
#define ff first
#define ss second
#define pb push_back
#define all(x) (x).begin(), (x).end()
#define sz(x) (int)(x).size()

typedef long long int lli;
typedef vector<lli> vi;
typedef pair<lli,lli> ii;
typedef vector<ii> vii;

//    cout<<setprecision(9);
//    cout<<fixed;

#define trace(args...) { string  _s =#args; replace(_s.begin(), _s.end(), ',',' '); stringstream _ss(_s); istream_iterator<string> _it(_ss); err(_it, args);}
void err(istream_iterator<string> it){}
template<typename T, typename... Args>
void err(istream_iterator<string> it, T a, Args... args){
  cerr <<  *it  << " : " << a << endl;
  err(++it, args...);
}
#define RAYA cerr<<"========================="<<endl;
template<typename T>
ostream & operator <<(ostream &os, const vector<T>&v){
  os << "[";
  rep(i,0,v.size()){
    if(i>0) os<<",";
    os<<v[i];
  }
  return os<<"]";
}
