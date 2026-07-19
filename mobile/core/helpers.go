package asenacore

import (
	"encoding/json"
	"net/netip"
	"strings"
	"sync"
	"time"
)

// ipSet — blacklist domainlerin çözülmüş IP'leri (TTL'li, thread-safe). Masaüstü nftset karşılığı.
type ipSet struct {
	mu sync.RWMutex
	m  map[netip.Addr]time.Time // IP -> son geçerlilik
}

func newIPSet() *ipSet { return &ipSet{m: make(map[netip.Addr]time.Time)} }

func (s *ipSet) AddAll(ips []netip.Addr, ttl time.Duration) {
	exp := time.Now().Add(ttl)
	s.mu.Lock()
	for _, ip := range ips {
		if cur, ok := s.m[ip]; !ok || exp.After(cur) {
			s.m[ip] = exp
		}
	}
	s.mu.Unlock()
}

func (s *ipSet) Contains(ip netip.Addr) bool {
	s.mu.RLock()
	exp, ok := s.m[ip]
	s.mu.RUnlock()
	if !ok {
		return false
	}
	if time.Now().After(exp) {
		s.mu.Lock()
		delete(s.m, ip)
		s.mu.Unlock()
		return false
	}
	return true
}

// matcher — apex ("site.com") + subdomain ("a.site.com") eşleştirir. Wildcard "*.site.com"
// blacklist'te "site.com" olarak saklanır (parseBlacklist normalize eder).
type matcher struct{ set map[string]struct{} }

func newMatcher(domains []string) *matcher {
	m := &matcher{set: make(map[string]struct{}, len(domains))}
	for _, d := range domains {
		m.set[d] = struct{}{}
	}
	return m
}

func (m *matcher) Match(host string) bool {
	host = strings.ToLower(strings.TrimSuffix(host, "."))
	// host ve her üst-alanını dene: a.b.site.com -> a.b.site.com, b.site.com, site.com
	for {
		if _, ok := m.set[host]; ok {
			return true
		}
		i := strings.IndexByte(host, '.')
		if i < 0 {
			return false
		}
		host = host[i+1:]
	}
}

// parseBlacklist — JSON dizisi (["x.com","*.y.com","# yorum"]) -> normalize domain listesi.
// '*.'/baş-son nokta/boş/yorum temizlenir (masaüstü state.py normalize_domain ile aynı ruh).
func parseBlacklist(js string) []string {
	var raw []string
	if err := json.Unmarshal([]byte(js), &raw); err != nil {
		return nil
	}
	out := make([]string, 0, len(raw))
	seen := make(map[string]struct{})
	for _, d := range raw {
		d = strings.TrimSpace(strings.SplitN(d, "#", 2)[0])
		d = strings.TrimPrefix(d, "*.")
		d = strings.Trim(strings.ToLower(d), ".")
		if d == "" || !strings.Contains(d, ".") {
			continue
		}
		if _, ok := seen[d]; ok {
			continue
		}
		seen[d] = struct{}{}
		out = append(out, d)
	}
	return out
}
