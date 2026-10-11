" Sourced from ~/.vimrc. For .cpp files under this folder:
"   <Space>t   save, compile, run the samples in a split (same as `make <file>`)
"   <Space>q   close that split
"   <Space>c   copy the whole file to the clipboard (what is on screen, saved or not)
let s:root = expand('<sfile>:p:h')

function! s:Close() abort
  if exists('s:buf') && bufexists(s:buf)
    execute 'bwipeout!' s:buf
  endif
endfunction

function! s:Test() abort
  write
  call s:Close()
  " beside the code when the terminal is wide enough, below it otherwise
  let l:opts = {'cwd': expand('%:p:h'), 'term_name': 'samples'}
  if &columns >= 150
    call extend(l:opts, {'vertical': 1, 'term_cols': min([&columns * 2 / 5, 100])})
  else
    call extend(l:opts, {'term_rows': &lines / 2})
  endif
  botright let s:buf = term_start(['make', '-s', '-f', s:root . '/Makefile', expand('%:t:r')], l:opts)
  setlocal nonumber norelativenumber
  wincmd p
endfunction

function! s:Copy() abort
  call system('pbcopy', join(getline(1, '$'), "\n") . "\n")
  echo 'copied ' . expand('%:t') . ' (' . line('$') . ' lines)'
endfunction

augroup cp_samples
  autocmd!
  execute 'autocmd BufRead,BufNewFile' fnameescape(s:root) . '/*.cpp nnoremap <buffer> <silent> <Space>t :call <SID>Test()<CR>'
  execute 'autocmd BufRead,BufNewFile' fnameescape(s:root) . '/*.cpp nnoremap <buffer> <silent> <Space>q :call <SID>Close()<CR>'
  execute 'autocmd BufRead,BufNewFile' fnameescape(s:root) . '/*.cpp nnoremap <buffer> <silent> <Space>c :call <SID>Copy()<CR>'
augroup END
