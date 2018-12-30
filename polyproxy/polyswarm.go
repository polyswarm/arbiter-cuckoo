// Copyright (C) 2018 Hatching B.V.
// All rights reserved.

// HTTP request helper

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"net/url"
	"time"

	"golang.org/x/sync/semaphore"
)

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
	return &Request{err, req, nil, nil}
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

func (r *Request) Raw() (PolyResp, error) {
	defer r.Close()
	var pr PolyResp
	if r.err != nil {
		return pr, r.err
	}
	resp, err := http.DefaultClient.Do(r.req) // TODO: client?
	if err != nil {
		r.err = err
		return pr, r.err
	}
	r.resp = resp
	pr.statusCode = resp.StatusCode
	body, _ := ioutil.ReadAll(resp.Body)
	pr.raw = body
	if err := json.Unmarshal(body, &pr); err == nil {
		// Valid JSON body
		if resp.StatusCode < 200 || resp.StatusCode > 299 {
			r.err = pr
			return pr, r.err
		}
	} else {
		pr.decodeErr = err
		r.err = pr
		return pr, r.err
	}
	return pr, r.err
}

func (r *Request) Read(v interface{}) error {
	pr, err := r.Raw()
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
