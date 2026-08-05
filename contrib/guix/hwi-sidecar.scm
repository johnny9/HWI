;;; Copyright (c) 2026 The HWI developers
;;; Distributed under the MIT software license, see the accompanying
;;; file LICENSE or http://www.opensource.org/licenses/mit-license.php.

(use-modules (gnu packages base)
             (gnu packages compression)
             (gnu packages finance)
             (gnu packages libusb)
             (gnu packages protobuf)
             (gnu packages python)
             (gnu packages python-build)
             (gnu packages python-crypto)
             (gnu packages python-web)
             (gnu packages python-xyz)
             (guix build-system gnu)
             (guix build-system pyproject)
             (guix download)
             (guix gexp)
             (guix git-download)
             ((guix licenses) #:prefix license:)
             (guix packages)
             (ice-9 ftw))

(define hwi-version "3.2.0")
(define source-date-epoch
  (or (getenv "SOURCE_DATE_EPOCH") "1546300800"))
(define repository-root
  (canonicalize-path
   (string-append (dirname (current-filename)) "/../..")))
(define repository-predicate
  (or (git-predicate repository-root)
      (lambda (_file _stat) #t)))
(define use-glibc-2.35
  ;; Keep the sidecar compatible with the glibc baseline enforced by the
  ;; Bitcoin Core integration PoC instead of inheriting Guix's rolling libc.
  (package-input-rewriting `((,glibc . ,glibc-2.35))))

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

(define hwi-sidecar
 (package
  (name "hwi-sidecar")
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
                (guix build utils))
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
            (let ((libusb (search-input-file inputs "/lib/libusb-1.0.so.0")))
              (mkdir-p "/tmp/hwi-home")
              (setenv "HOME" "/tmp/hwi-home")
              (setenv "LC_ALL" "C")
              (setenv "PYTHONHASHSEED" "0")
              (setenv "PYTHONNOUSERSITE" "1")
              (setenv "PYINSTALLER_CONFIG_DIR" "/tmp/hwi-pyinstaller")
              (setenv "SOURCE_DATE_EPOCH" #$source-date-epoch)
              (setenv "HWI_LIBUSB_PATH" libusb)
              (invoke "pyinstaller" "--clean" "--noconfirm"
                      "hwi-sidecar.spec")
              (invoke "python3" "contrib/generate_sidecar_manifest.py"
                      "dist/hwi"
                      "--platform" "linux"
                      "--architecture" "x86_64"))))
        (replace 'check
          (lambda _
            (invoke "python3" "-m" "unittest"
                    "test.test_sidecar_manifest"
                    "test.test_sidecar_archive")
            (invoke "dist/hwi/hwi" "--version")))
        (replace 'install
          (lambda _
            (let ((archive
                   (string-append #$output "/hwi-" #$hwi-version
                                  "-x86_64-linux-gnu.tar.gz")))
              (mkdir-p #$output)
              (copy-recursively "dist/hwi" (string-append #$output "/hwi"))
              (invoke "python3" "contrib/package_sidecar.py"
                      "dist/hwi" archive
                      "--source-date-epoch" #$source-date-epoch)))))))
  (native-inputs
   (list libusb
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
         python-typing-extensions))
  (supported-systems '("x86_64-linux"))
  (home-page "https://github.com/bitcoin-core/HWI")
  (synopsis "Reproducible headless HWI sidecar")
  (description
   "Build the headless HWI PyInstaller sidecar and its canonical unsigned
manifest in an isolated Guix environment, then package it as a normalized
archive for independent reproduction.")
  (license license:expat)))

(use-glibc-2.35 hwi-sidecar)
