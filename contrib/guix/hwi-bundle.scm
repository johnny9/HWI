;;; Copyright (c) 2026 The HWI developers
;;; Distributed under the MIT software license, see the accompanying
;;; file LICENSE or http://www.opensource.org/licenses/mit-license.php.

(use-modules (gnu packages)
             (gnu packages base)
             (gnu packages compression)
             (gnu packages commencement)
             (gnu packages cross-base)
             (gnu packages elf)
             (gnu packages finance)
             (gnu packages libffi)
             (gnu packages libusb)
             ((gnu packages linux) #:select (linux-libre-headers-6.1))
             (gnu packages protobuf)
             (gnu packages python)
             (gnu packages python-build)
             (gnu packages python-crypto)
             (gnu packages python-web)
             (gnu packages python-xyz)
             (gnu packages tls)
             (gnu packages xml)
             (guix build-system cargo)
             (guix build-system gnu)
             (guix build-system pyproject)
             (guix build-system python)
             (guix build-system trivial)
             (guix download)
             (guix gexp)
             (guix git-download)
             (guix memoization)
             ((guix licenses) #:prefix license:)
             (guix packages)
             ((guix utils) #:select (nix-system->gnu-triplet
                                     substitute-keyword-arguments))
             (ice-9 ftw)
             (ice-9 match)
             (srfi srfi-1))

(define hwi-version "3.2.0")
(define source-date-epoch
  (or (getenv "SOURCE_DATE_EPOCH") "1546300800"))
(define repository-root
  (canonicalize-path
   (string-append (dirname (current-filename)) "/../..")))
(define repository-predicate
  (or (git-predicate repository-root)
      (lambda (_file _stat) #t)))

(define target-triple
  (or (getenv "HWI_TARGET") "x86_64-linux-gnu"))
(define target-configurations
  '(("x86_64-linux-gnu" "x86_64-linux" "x86_64"
     "/lib64/ld-linux-x86-64.so.2")
    ("arm-linux-gnueabihf" "armhf-linux" "arm"
     "/lib/ld-linux-armhf.so.3")
    ("aarch64-linux-gnu" "aarch64-linux" "aarch64"
     "/lib/ld-linux-aarch64.so.1")
    ("riscv64-linux-gnu" "riscv64-linux" "riscv64"
     "/lib/ld-linux-riscv64-lp64d.so.1")))
(define target-configuration
  (or (assoc target-triple target-configurations)
      (error "unsupported Guix HWI target" target-triple)))
(define target-system (cadr target-configuration))
(define target-architecture (caddr target-configuration))
(define target-interpreter (cadddr target-configuration))
(define target-store-interpreter
  (string-append "/lib/" (basename target-interpreter)))

(define-syntax-rule (search-our-patches file-name ...)
  (parameterize
      ((%patch-path
        (list (string-append (dirname (current-filename)) "/patches"))))
    (list (search-patch file-name) ...)))

(define building-on
  ;; Guix evaluates this file on the runner before lowering the package for
  ;; --system.  For QEMU-backed ARM and RISC-V builds, %current-system is
  ;; therefore the x86_64 runner rather than the system that executes the
  ;; package build.  Use the selected target system for glibc's build triplet.
  (string-append "--build=" (nix-system->gnu-triplet target-system)))

(define glibc-2.31-for-bitcoin-core
  ;; This is the same glibc source, hardening configuration, and RISC-V fix
  ;; used by Bitcoin Core's Guix toolchains.  Keeping the recipe here makes
  ;; HWI, rather than Bitcoin Core, responsible for the bundle ABI contract.
  (let ((commit "28eb5caf895ced5d895cb02757e109004a2d33e5"))
    (package
      (inherit glibc)
      (version "2.31")
      (source
       (origin
         (method git-fetch)
         (uri (git-reference
               (url "https://sourceware.org/git/glibc.git")
               (commit commit)))
         (file-name (git-file-name "glibc" commit))
         (sha256
          (base32
           "07arjrc1smqy8wrhg38apr1s9ji7xv1rpzdapk4k2ps2n07irp58"))
         (patches
          (search-our-patches "glibc-guix-prefix.patch"
                              "glibc-riscv-jumptarget.patch"))))
      (arguments
       (substitute-keyword-arguments (package-arguments glibc)
         ((#:configure-flags flags)
          `(append ,flags
                   (list "--enable-stack-protector=all"
                         "--enable-cet"
                         "--enable-bind-now"
                         "--disable-werror"
                         "--disable-timezone-tools"
                         "--disable-profile"
                         ,building-on)))
         ((#:phases phases)
          `(modify-phases ,phases
             (add-before 'configure 'use-c-support-link-test
               (lambda _
                 ;; Bitcoin Core normally builds this libc with a C-only
                 ;; cross compiler.  A native build would otherwise link this
                 ;; non-installed helper against the host libstdc++, whose
                 ;; newer GLIBC symbol requirements cannot be satisfied by
                 ;; glibc 2.31.
                 (substitute* "support/Makefile"
                   (("^LINKS_DSO_PROGRAM = links-dso-program\n")
                    "LINKS_DSO_PROGRAM = links-dso-program-c\n"))))
             (add-before 'configure 'set-etc-rpc-installation-directory
               (lambda* (#:key outputs #:allow-other-keys)
                 (let ((out (assoc-ref outputs "out")))
                   (substitute* "sunrpc/Makefile"
                     (("^\\$\\(inst_sysconfdir\\)/rpc(.*)$" _ suffix)
                      (string-append out "/etc/rpc" suffix "\n"))
                     (("^install-others =.*$")
                      (string-append "install-others = " out "/etc/rpc\n"))))))
             ;; This phase in the current Guix glibc package embeds that
             ;; package's 2.41 version and locale layout.  The bundle does
             ;; not ship locale data, so it does not apply to this 2.31 libc.
             (delete 'install-utf8-c-locale))))))))

(define (make-bitcoin-core-glibc-toolchain target)
  ;; Bootstrap the target compiler without a libc first.  Building a native
  ;; GCC directly against glibc 2.31 would pull in Guix's newer host libgcc,
  ;; which itself requires post-2.31 symbols.
  (let* ((xbinutils (cross-binutils target))
         (xgcc-sans-libc
          (cross-gcc target
                     #:xbinutils xbinutils))
         (xkernel
          (cross-kernel-headers target
                                #:linux-headers linux-libre-headers-6.1
                                #:xgcc xgcc-sans-libc
                                #:xbinutils xbinutils))
         (xlibc
          (cross-libc target
                      #:libc glibc-2.31-for-bitcoin-core
                      #:xgcc xgcc-sans-libc
                      #:xbinutils xbinutils
                      #:xheaders xkernel))
         (xgcc
          (cross-gcc target
                     #:xbinutils xbinutils
                     #:libc xlibc)))
    (package
      (name (string-append target "-glibc-2.31-native-toolchain"))
      (version (package-version xgcc))
      (source #f)
      (build-system trivial-build-system)
      (arguments
       (list
        #:modules '((guix build union)
                    (guix build utils))
        #:builder
        #~(begin
            (use-modules (guix build union)
                         (guix build utils))
            ;; Match Guix's cross-gcc-toolchain contract so the CROSS_*
            ;; search paths below resolve both compiler and libc contents.
            (union-build #$output
                         (list #$xbinutils #$xgcc #$xkernel #$xlibc))
            (let ((bindir (string-append #$output "/bin"))
                  (prefix (string-append #$target-triple "-")))
              (for-each
               (lambda (alias program)
                 (symlink (string-append #$xgcc "/bin/" prefix program)
                          (string-append bindir "/" alias)))
               '("gcc" "cc" "g++" "c++" "cpp" "gcc-ar" "gcc-nm"
                 "gcc-ranlib")
               '("gcc" "gcc" "g++" "g++" "cpp" "gcc-ar" "gcc-nm"
                 "gcc-ranlib"))
              (for-each
               (lambda (program)
                 (symlink (string-append #$xbinutils "/bin/" prefix program)
                          (string-append bindir "/" program)))
               '("ar" "as" "ld" "nm" "objcopy" "objdump" "ranlib"
                 "readelf" "strip"))))))
      (inputs (list xbinutils xkernel xlibc xgcc))
      (native-search-paths (package-search-paths xgcc))
      (synopsis "Native aliases for the Bitcoin Core glibc toolchain")
      (description
       "Expose a same-architecture Bitcoin Core cross toolchain under native
compiler names so PyInstaller and Python extension builds target glibc 2.31.")
      (home-page "https://bitcoincore.org")
      (license license:gpl3+))))

(define bitcoin-core-glibc-toolchain
  (make-bitcoin-core-glibc-toolchain target-triple))

(define bitcoin-core-toolchain-inputs
  `(("gcc-toolchain" ,bitcoin-core-glibc-toolchain)))

(define bitcoin-core-cargo-toolchain-inputs
  `(("gcc" ,bitcoin-core-glibc-toolchain)
    ;; Cargo's configure phase resolves the compiler through an input named
    ;; "gcc".  Retain the combined-toolchain label so its search paths match
    ;; those used by every other package in the runtime graph.
    ("gcc-toolchain" ,bitcoin-core-glibc-toolchain)))

;; Rebuild the packages whose outputs are copied into the bundle with the
;; pinned libc toolchain.  Native inputs remain on Guix's host toolchain:
;; they execute only while building and are not shipped in the archive.
(define (rewrite-runtime-input input)
  (match input
    ((label (? package? package) outputs ...)
     `(,label ,(rewrite-runtime-package package) ,@outputs))
    (_ input)))

(define rewrite-runtime-package
  (mlambda (package)
    (if (string=? (package-name package) "glibc")
        glibc-2.31-for-bitcoin-core
        (let ((runtime-package
               (cond
                ((string=? (package-name package) "abseil-cpp")
                   ;; GoogleTest is a build-only input compiled with Guix's
                   ;; host libc.  Runtime Abseil does not need it, and its
                   ;; inherited global linker flags would otherwise make the
                   ;; old-libc compiler probe try to link against it.
                   (package/inherit package
                     (arguments
                      (substitute-keyword-arguments
                          (package-arguments package)
                        ((#:tests? _ #t) #f)
                        ((#:configure-flags flags #~'())
                         #~(append #$flags
                                   (list "-DABSL_BUILD_TESTING=OFF"
                                         "-DABSL_USE_EXTERNAL_GOOGLETEST=OFF"
                                         "-DCMAKE_EXE_LINKER_FLAGS=")))))))
                ((string=? (package-name package) "bzip2")
                 ;; Guix's phase normally hides the implicit build-time bzip2
                 ;; from LIBRARY_PATH.  This compiler intentionally publishes
                 ;; the equivalent cross-prefixed search variable instead.
                 (package/inherit package
                   (arguments
                    (substitute-keyword-arguments
                        (package-arguments package)
                      ((#:phases phases)
                       #~(modify-phases #$phases
                           (replace 'hide-input-bzip2
                             (lambda* (#:key inputs #:allow-other-keys)
                               (let ((bzip2 (assoc-ref inputs "bzip2")))
                                 (when bzip2
                                   (for-each
                                    (lambda (variable)
                                      (let ((value (getenv variable)))
                                        (when value
                                          (setenv
                                           variable
                                           (string-join
                                            (delete
                                             (string-append bzip2 "/lib")
                                             (string-split value #\:))
                                            ":")))))
                                    '("LIBRARY_PATH"
                                      "CROSS_LIBRARY_PATH"))))))))))))
                ((string=? (package-name package) "protobuf")
                 ;; Guix's Protobuf tests depend on Abseil's GoogleTest-only
                 ;; scoped_mock_log target.  The runtime graph deliberately
                 ;; omits those host-toolchain test libraries, so configure
                 ;; only the shared Protobuf library used by python-protobuf.
                 (package/inherit package
                   (arguments
                    (substitute-keyword-arguments
                        (package-arguments package)
                      ((#:tests? _ #t) #f)
                      ((#:configure-flags flags #~'())
                       #~(cons "-Dprotobuf_BUILD_TESTS=OFF" #$flags))))))
                ((string=? (package-name package) "util-linux")
                 ;; The lsfd option-inet test waits indefinitely for helper
                 ;; sockets inside rootless container builders.  util-linux is
                 ;; only a transitive runtime input of eudev here, so skip its
                 ;; environment-sensitive system test suite.
                 (package/inherit package
                   (arguments
                    (substitute-keyword-arguments
                        (package-arguments package)
                      ((#:tests? _ #t) #f)))))
                ((string=? (package-name package) "python-cryptography")
                 ;; cryptography is a pyproject package, but Maturin launches
                 ;; Cargo while building its Rust extension.  It therefore
                 ;; needs the same explicit rustc linker pin as native Cargo
                 ;; packages even though its outer build system is Python.
                 (package/inherit package
                   (arguments
                    (substitute-keyword-arguments
                        (package-arguments package)
                      ((#:phases phases)
                       #~(modify-phases #$phases
                           (add-before 'build 'use-pinned-rust-linker
                             (lambda* (#:key inputs #:allow-other-keys)
                               (let ((gcc
                                      (assoc-ref inputs "gcc-toolchain")))
                                 (setenv
                                  "RUSTFLAGS"
                                  (string-append
                                   (or (getenv "RUSTFLAGS") "")
                                   " -C linker=" gcc "/bin/gcc")))))))))))
                ((string=? (package-name package) "python-cffi")
                 ;; CFFI's embedding tests link test DSOs to the build-side
                 ;; libpython.  That interpreter intentionally comes from
                 ;; Guix's native inputs and uses the host libc, so it cannot
                 ;; be linked by the glibc 2.31 target compiler.  The regular
                 ;; ABI/API suites still compile and exercise the target CFFI
                 ;; extension; only the host-interpreter embedding tests are
                 ;; inapplicable to this same-architecture cross build.
                 (package/inherit package
                   (arguments
                    (substitute-keyword-arguments
                        (package-arguments package)
                      ((#:phases phases)
                       #~(modify-phases #$phases
                           (add-before 'check 'remove-embedding-tests
                             (lambda _
                               (delete-file-recursively
                                "testing/embedding")))))))))
                ((string=? (package-name package) "python")
                 ;; HWI is a headless command-line application.  Omitting the
                 ;; optional tkinter and IDLE outputs prevents the portable
                 ;; interpreter from pulling Tcl, Tk, and the X11 stack into
                 ;; every target build.  Disable the optional LZMA module too:
                 ;; XZ is a build-side Guix tool rather than a declared Python
                 ;; input, and auto-detecting it would leak the host libc into
                 ;; the portable interpreter.
                 (package/inherit package
                   (outputs
                    (fold delete (package-outputs package)
                          '("tk" "idle")))
                   (arguments
                    (substitute-keyword-arguments
                        (package-arguments package)
                      ((#:configure-flags flags #~'())
                       #~(cons "py_cv_module__lzma=n/a" #$flags))))
                   (inputs
                    (filter
                     (match-lambda
                       ((label _ outputs ...)
                        (not (member label '("tcl" "tk"))))
                       (_ #t))
                     (package-inputs package)))))
                ((eq? (package-build-system package) cargo-build-system)
                 ;; Cargo sets CC for C build scripts but, for a native Rust
                 ;; target, rustc still finds the first gcc on PATH as its
                 ;; final linker.  That can select Guix's host libgcc and add
                 ;; GLIBC_2.34+ references.  Make every shipped Rust artifact
                 ;; and same-architecture build script use the pinned linker.
                 (package/inherit package
                   (arguments
                    (substitute-keyword-arguments
                        (package-arguments package)
                      ((#:phases phases)
                       #~(modify-phases #$phases
                           (add-after 'configure 'use-pinned-rust-linker
                             (lambda* (#:key inputs #:allow-other-keys)
                               (let ((gcc (assoc-ref inputs "gcc")))
                                 (setenv
                                  "RUSTFLAGS"
                                  (string-append
                                   (or (getenv "RUSTFLAGS") "")
                                   " -C linker=" gcc "/bin/gcc")))))))))))
                (else package))))
          (package-with-c-toolchain
           (package/inherit runtime-package
             (inputs
              (map rewrite-runtime-input
                   (package-inputs runtime-package)))
             (propagated-inputs
              (map rewrite-runtime-input
                   (package-propagated-inputs runtime-package))))
           (if (eq? (package-build-system runtime-package)
                    cargo-build-system)
               bitcoin-core-cargo-toolchain-inputs
               bitcoin-core-toolchain-inputs))))))

(define python-cbor2-for-hwi
  (package
    (inherit python-cbor2)
    (version "5.6.0")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "cbor2" version))
       (sha256
        (base32 "00nh74233m4c84ka2g0cq5v2xq5zp43hxcjspbyr4mwgdwif554x"))))))

(define python-pyinstaller-hooks-contrib
  (package
    (name "python-pyinstaller-hooks-contrib")
    (version "2024.0")
    (source
     (origin
       (method url-fetch)
       (uri
        (string-append
         "https://files.pythonhosted.org/packages/source/p/"
         "pyinstaller-hooks-contrib/pyinstaller-hooks-contrib-"
         version ".tar.gz"))
       (sha256
        (base32 "1c4636vg1hbf5wv45szcw5cnsysvga50bba3big5k24pbhd8q4d7"))))
    (build-system pyproject-build-system)
    (arguments (list #:tests? #f))
    (native-inputs (list python-setuptools python-wheel))
    (propagated-inputs (list python-packaging python-setuptools))
    (home-page "https://github.com/pyinstaller/pyinstaller-hooks-contrib")
    (synopsis "Community-maintained hooks for PyInstaller")
    (description
     "This package provides community-maintained module hooks for PyInstaller.")
    (license (list license:asl2.0 license:gpl2))))

(define python-pyinstaller-for-hwi
  (package
    (name "python-pyinstaller")
    (version "6.3.0")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "pyinstaller" version))
       (sha256
        (base32 "1pvk8akrxagsrxzp3l4jnmxyc2dyzf1dsbsmmhvjwiwrrjb4qkci"))))
    (build-system pyproject-build-system)
    (arguments
     (list
      #:tests? #f
      #:phases
      #~(modify-phases %standard-phases
          (add-before 'build 'compile-bootloader-from-source
            (lambda _
              (setenv "PYINSTALLER_COMPILE_BOOTLOADER" "1"))))))
    (native-inputs (list python-setuptools python-wheel))
    (inputs (list zlib))
    (propagated-inputs
     (list python-altgraph
           python-packaging
           python-pyinstaller-hooks-contrib
           python-setuptools))
    (home-page "https://pyinstaller.org/")
    (synopsis "Bundle a Python application and its dependencies")
    (description
     "PyInstaller analyzes Python applications and creates self-contained
application bundles.  This variant always compiles its bootloader from source.")
    (license license:gpl2+)))

(define hwi-bundle
 (package
  (name "hwi-bundle")
  (version hwi-version)
  (source
   (local-file repository-root
               "hwi-source"
               #:recursive? #t
               #:select? repository-predicate))
  (build-system gnu-build-system)
  (arguments
   (list
    #:tests? #f
    #:modules '((guix build gnu-build-system)
                (guix build utils)
                (ice-9 popen)
                (ice-9 rdelim))
    #:phases
    #~(modify-phases %standard-phases
        (replace 'unpack
          (lambda* (#:key source #:allow-other-keys)
            ;; PyInstaller can retain source paths.  Use the same build path on
            ;; every worker rather than Guix's per-build temporary directory.
            (mkdir-p "/tmp/hwi-build")
            (copy-recursively source "/tmp/hwi-build")
            (chdir "/tmp/hwi-build")))
        (delete 'configure)
        (replace 'build
          (lambda* (#:key inputs #:allow-other-keys)
            (let* ((libusb
                    (search-input-file inputs "/lib/libusb-1.0.so.0"))
                   (python (assoc-ref inputs "python"))
                   (gcc-toolchain (assoc-ref inputs "gcc-toolchain"))
                   (libgcc
                    (let* ((port
                            (open-pipe*
                             OPEN_READ
                             (string-append gcc-toolchain "/bin/gcc")
                             "-print-file-name=libgcc_s.so.1"))
                           (path (read-line port))
                           (status (close-pipe port)))
                      (unless (zero? status)
                        (error "failed to locate target libgcc_s"))
                      path))
                   (runtime-libraries
                    (list
                     (search-input-file inputs "/lib/libbz2.so.1.0")
                     (search-input-file inputs "/lib/libcrypto.so.3")
                     (search-input-file inputs "/lib/libexpat.so.1")
                     (search-input-file inputs "/lib/libffi.so.8")
                     libgcc
                     (search-input-file
                      inputs "/lib/libhidapi-libusb.so.0")
                     (search-input-file inputs "/lib/libssl.so.3")
                     (search-input-file inputs "/lib/libz.so.1"))))
              (mkdir-p "/tmp/hwi-home")
              (setenv "HOME" "/tmp/hwi-home")
              (setenv "LC_ALL" "C")
              (setenv "PYTHONHASHSEED" "0")
              (setenv "PYTHONNOUSERSITE" "1")
              (setenv "PYINSTALLER_CONFIG_DIR" "/tmp/hwi-pyinstaller")
              (setenv "SOURCE_DATE_EPOCH" #$source-date-epoch)
              (setenv "HWI_LIBUSB_PATH" libusb)
              ;; The generated pyinstaller console script is installed by a
              ;; Python build system and can retain its build-side shebang.
              ;; Launch the module with the explicitly rewritten interpreter
              ;; so its bundled libpython cannot come from the host libc.
              (invoke (string-append python "/bin/python3")
                      "-m" "PyInstaller" "--clean" "--noconfirm"
                      "hwi-bundle.spec")
              ;; PyInstaller treats several shared objects as Linux system
              ;; libraries and omits them.  They are not stable across our
              ;; supported distributions, so ship the pinned Guix copies.
              (for-each
               (lambda (library)
                 (copy-file
                  library
                  (string-append "dist/hwi/_internal/"
                                 (basename library))))
               runtime-libraries)
              (chmod "dist/hwi/hwi" #o755)
              ;; Guix links executables to a store-specific loader.  The
              ;; released bundle must instead use the target's conventional
              ;; loader and find its bundled libraries relative to itself.
              (invoke "patchelf"
                      "--set-interpreter" #$target-interpreter
                      "--set-rpath" "$ORIGIN/_internal"
                      "dist/hwi/hwi")
              (invoke "python3" "contrib/generate_bundle_manifest.py"
                      "dist/hwi"
                      "--platform" "linux"
                      "--architecture" #$target-architecture))))
        (replace 'check
          (lambda _
            (invoke "python3" "-m" "unittest"
                    "test.test_bundle_manifest"
                    "test.test_bundle_archive")))
        (replace 'install
          (lambda* (#:key inputs #:allow-other-keys)
            (let* ((installed-bundle (string-append #$output "/hwi"))
                   (installed-entrypoint
                    (string-append installed-bundle "/hwi"))
                   (build-interpreter
                    (search-input-file inputs #$target-store-interpreter))
                   (archive
                    (string-append #$output "/hwi-" #$hwi-version
                                   "-" #$target-triple ".tar.gz")))
              (mkdir-p #$output)
              (copy-recursively "dist/hwi" installed-bundle)
              ;; Guix 1.5's AppArmor profile forbids executing files created
              ;; under /tmp, but permits execution from the store output.
              ;; Probe the exact installed entry point rather than the copy in
              ;; the fixed, reproducible PyInstaller build directory.  Patch
              ;; in the store loader only for the probe: invoking ld-linux as
              ;; the program makes PyInstaller resolve /proc/self/exe to the
              ;; loader and prevents it from finding its appended archive.
              (invoke "patchelf"
                      "--set-interpreter" build-interpreter
                      installed-entrypoint)
              (invoke installed-entrypoint "--version")
              (invoke "patchelf"
                      "--set-interpreter" #$target-interpreter
                      installed-entrypoint)
              (invoke "python3" "contrib/package_bundle.py"
                      "dist/hwi" archive
                      "--source-date-epoch" #$source-date-epoch)))))))
  (inputs
   (list bzip2
         expat
         glibc-2.31-for-bitcoin-core
         hidapi
         libffi
         libusb
         openssl
         python
         python-cbor2-for-hwi
         python-ecdsa
         python-hidapi
         python-libusb1
         python-mnemonic
         python-noiseprotocol
         python-protobuf-6
         python-pyaes
         python-pyinstaller-for-hwi
         python-pyserial
         python-semver
         python-typing-extensions
         zlib))
  (native-inputs (list patchelf))
  (supported-systems (list target-system))
  (home-page "https://github.com/bitcoin-core/HWI")
  (synopsis "Reproducible headless HWI bundle")
  (description
   "Build the headless HWI PyInstaller bundle and its canonical unsigned
manifest in an isolated Guix environment, then package it as a normalized
archive for independent reproduction.")
  (license license:expat)))

(rewrite-runtime-package hwi-bundle)
