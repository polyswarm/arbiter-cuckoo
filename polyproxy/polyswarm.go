// Copyright (C) 2018 Hatching B.V.
// All rights reserved.

// HTTP request helper

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"

	"golang.org/x/sync/semaphore"
)

var hclient = http.Client{
	Transport: &http.Transport{
		DisableKeepAlives: true,
	},
}

// Fairly short, and should not be used in production, but chosen to deal with
// potential remote load balancer issues
var (
	PolyswarmTimeoutNonTX = time.Second * 5
	PolyswarmTimeoutTX    = time.Second * 30
)

type Polyswarm struct {
	Limit *semaphore.Weighted

	URL        string
	BearerAuth string
	Account    string
}

type PolyResp struct {
	statusCode int
	raw        []byte
	decodeErr  error

	Status string          `json:"status,omitempty"`
	Errors json.RawMessage `json:"errors,omitempty"`
	Result json.RawMessage `json:"result,omitempty"`
}

func (pr PolyResp) Error() string {
	if pr.decodeErr != nil {
		fmt.Printf("RAW: %q\n", string(pr.raw))
		return fmt.Sprintf("%v: %v", pr.statusCode, pr.decodeErr)
	}
	if len(pr.Errors) == 0 {
		if len(pr.Status) > 0 {
			return fmt.Sprintf("%v: %v", pr.statusCode, pr.Status)
		}
		if len(pr.raw) > 0 {
			return fmt.Sprintf("%v: %q", pr.statusCode, string(pr.raw))
		}
		return fmt.Sprintf("%v: unknown error", pr.statusCode)
	}
	return string(pr.Errors)
}

func (pr PolyResp) Unmarshal(v interface{}) error {
	return json.Unmarshal(pr.Result, v)
}

func (ps *Polyswarm) Nonce(chain string) (uint64, error) {
	u := fmt.Sprintf(
		"/nonce?account=%v&chain=%v",
		url.QueryEscape(ps.Account),
		url.QueryEscape(chain),
	)
	var nonce uint64
	err := ps.Request("GET", u).Timeout(PolyswarmTimeoutNonTX).Read(&nonce)
	return nonce, err
}

type Request struct {
	ps     *Polyswarm
	err    error
	req    *http.Request
	resp   *http.Response
	cancel context.CancelFunc
}

func (ps *Polyswarm) Request(method, path string) *Request {
	req, err := http.NewRequest(method, ps.URL+path, nil)
	if req != nil && ps.BearerAuth != "" {
		req.Header.Set("Authorization", "Bearer "+ps.BearerAuth)
	}
	return &Request{ps, err, req, nil, nil}
}

func (r *Request) Timeout(t time.Duration) *Request {
	ctx, cancel := context.WithTimeout(context.Background(), t)
	r.cancel = cancel
	return r.WithContext(ctx)
}

func (r *Request) WithContext(ctx context.Context) *Request {
	r.req = r.req.WithContext(ctx)
	return r
}

// Set JSON body
func (r *Request) JSON(obj interface{}) *Request {
	if r.err != nil {
		return r
	}
	var b []byte
	if raw, ok := obj.(json.RawMessage); ok {
		b = raw
	} else {
		var err error
		b, err = json.Marshal(obj)
		if err != nil {
			r.err = err
			return r
		}
	}
	r.req.Header.Set("Content-Type", "application/json; charset=utf8")
	r.req.Body = ioutil.NopCloser(bytes.NewReader(b))
	r.req.ContentLength = int64(len(b))
	return r
}

func (r *Request) Close() {
	if r.cancel != nil {
		r.cancel()
		r.cancel = nil
	}
	if r.resp != nil && r.resp.Body != nil {
		r.resp.Body.Close()
	}
}

func (r *Request) Do() error {
	defer r.Close()
	return r.Read(nil)
}

func (r *Request) Err() error {
	return r.err
}

// Can return an error if nothing was proxied
func (r *Request) Raw(w http.ResponseWriter) (PolyResp, error) {
	r.ps.Limit.Acquire(context.TODO(), 1)
	defer r.ps.Limit.Release(1)
	defer r.Close()
	var pr PolyResp
	if r.err != nil {
		return pr, r.err
	}
	resp, err := hclient.Do(r.req)
	if err != nil {
		r.err = err
		return pr, r.err
	}
	r.resp = resp

	ct := resp.Header.Get("Content-Type")
	if w != nil {
		w.Header().Set("Content-Type", ct)
		w.WriteHeader(resp.StatusCode)
	}

	pr.statusCode = resp.StatusCode
	if strings.HasPrefix(ct, "application/json") {
		// Copy JSON body so we can inspect it

		// TODO: max resp. length
		var our io.Reader
		if w == nil {
			our = resp.Body
		} else {
			our = io.TeeReader(resp.Body, w)
		}
		body, _ := ioutil.ReadAll(our)
		pr.raw = body
		pr.decodeErr = json.Unmarshal(body, &pr)
	} else {
		log.Println("Non-JSON:", ct)
		if w != nil {
			_, r.err = io.Copy(w, resp.Body)
		}
	}

	return pr, nil
}

func (r *Request) Read(v interface{}) error {
	pr, err := r.Raw(nil)
	if err != nil {
		return err
	}
	if v != nil {
		err := json.Unmarshal(pr.Result, v)
		if err != nil {
			pr.decodeErr = err
			r.err = pr
		}
	}
	return r.err
}
