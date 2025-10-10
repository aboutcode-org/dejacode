# This file is used by `nix-build`.
# Update it manually whenever the version or dependencies change in `pyproject.toml`.

# For packages with pinned versions to match those in pyproject.toml.
# It's recommended to use pre-built wheels instead of building from source,
# as source builds may require additional dependencies.

# Run the following command to compute the sha256:
# nix-prefetch-url <url>
{
  pkgs ? import <nixpkgs> { },
}:

let
  python = pkgs.python313;

  # Helper function to override a package to disable tests
  disableAllTests =
    package: extraAttrs:
    package.overrideAttrs (
      old:
      {
        doCheck = false;
        doInstallCheck = false;
        doPytestCheck = false;
        pythonImportsCheck = [];
        checkPhase = "echo 'Tests disabled'";
        installCheckPhase = "echo 'Install checks disabled'";
        pytestCheckPhase = "echo 'Pytest checks disabled'";
        __intentionallyOverridingVersion = old.__intentionallyOverridingVersion or false;
      }
      // extraAttrs
    );

  pythonOverlay = self: super: {
    maturin = python.pkgs.buildPythonPackage rec {
      pname = "maturin";
      version = "1.8.6";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/f9/aa/8090f8b3f5f7ec46bc95deb0f5b29bf52c98156ef594f2e65d20bf94cea1/maturin-1.8.6-py3-none-manylinux_2_12_x86_64.manylinux2010_x86_64.musllinux_1_1_x86_64.whl";
        sha256 = "15870w46liwy15a5x81cpdb8f9b6k4sawzxii604r5bmcj699idy";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    rq-scheduler = python.pkgs.buildPythonPackage rec {
      pname = "rq-scheduler";
      version = "0.14.0";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/bb/d0/28cedca9f3b321f30e69d644c2dcd7097ec21570ec9606fde56750621300/rq_scheduler-0.14.0-py2.py3-none-any.whl";
        sha256 = "03fwqc7v4sp8jxmpnwyvacr7zqgikafz0hg0apzv64cc7ld25v6l";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    clamd = python.pkgs.buildPythonPackage rec {
      pname = "clamd";
      version = "1.0.2";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/3d/d0/84614de2a53ad52370adc9f9260bea420e53e0c228a248ec0eacfa65ccbb/clamd-1.0.2-py2.py3-none-any.whl";
        sha256 = "1rzmrwywx6rnzb62ca08xn0gkyq0kvbqka00pvb0zc0ygmmm8cjw";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    mockldap = python.pkgs.buildPythonPackage rec {
      pname = "mockldap";
      version = "0.3.0.post1";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/e3/6e/1536bc788db4cbccf3f2ffb37737af5e90f163ce69858f5aa1275981ed8a/mockldap-0.3.0.post1-py2.py3-none-any.whl";
        sha256 = "1n9q7girlpm97rva515q2y04bx2rhn431m996vc9b7xycq16mpnd";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    swapper = python.pkgs.buildPythonPackage rec {
      pname = "swapper";
      version = "1.4.0";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/e9/53/c59363308ef97507a680372471e25e1ebab2e706a45a7c416eea6474c928/swapper-1.4.0-py2.py3-none-any.whl";
        sha256 = "0pilp6agh0gfi0y0pllk6jv29vghrzlccbg35xa44hi3mn53gf2p";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    django-rest-hooks = python.pkgs.buildPythonPackage rec {
      pname = "django-rest-hooks";
      version = "1.6.1";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://github.com/aboutcode-org/django-rest-hooks/releases/download/1.6.1/django_rest_hooks-1.6.1-py2.py3-none-any.whl";
        sha256 = "1byakq3ghpqhm0mjjkh8v5y6g3wlnri2vvfifyi9ky36l12vqx74";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    aboutcode-toolkit = python.pkgs.buildPythonPackage rec {
      pname = "aboutcode-toolkit";
      version = "11.1.1";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/14/ee/ba139231e3de1287189c2f7940e7e0f8a135421050ff1b4f0145813ae8b9/aboutcode_toolkit-11.1.1-py3-none-any.whl";
        sha256 = "0bx32ca9m01grwn69594jb8fgcqbm3wnviadig5iw1fxx3hpgpmy";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    django-grappelli = python.pkgs.buildPythonPackage rec {
      pname = "django-grappelli";
      version = "4.0.2";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/79/66/bec8c43767f830d8c4884d8350d81e28043d3a04364b9fca43946d98a47e/django_grappelli-4.0.2-py2.py3-none-any.whl";
        sha256 = "1515f13pm2lc8830zsrjznsfbfnh6xfmp6gvzxcx6nh2ryiqf2pd";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    django-altcha = python.pkgs.buildPythonPackage rec {
      pname = "django-altcha";
      version = "0.3.0";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/9e/6e/ad184a95de2652f5834243f5b3403c8949993f5f3de08a5609b15a63b091/django_altcha-0.3.0-py3-none-any.whl";
        sha256 = "0gcgir468q5ra9blm00vgdij0avpsyscbadg5k69ra7kfr8q8jgw";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    jsonfield = python.pkgs.buildPythonPackage rec {
      pname = "jsonfield";
      version = "3.1.0";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/7c/97/3a4805532a9c1982368fd9f37b58133419e83704744b733ccab9e9827176/jsonfield-3.1.0-py3-none-any.whl";
        sha256 = "1vc9ss6k182qcfy70y54lyca6w2yh012x97vpabjn9bzb08pi1fz";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    pip = python.pkgs.buildPythonPackage rec {
      pname = "pip";
      version = "25.1.1";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/29/a2/d40fb2460e883eca5199c62cfc2463fd261f760556ae6290f88488c362c0/pip-25.1.1-py3-none-any.whl";
        sha256 = "1bsihxacxq9i14dv0x6y3vf56fvzjsgbs1xm9avackmz5a5a64r9";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    psycopg = python.pkgs.buildPythonPackage rec {
      pname = "psycopg";
      version = "3.2.9";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/44/b0/a73c195a56eb6b92e937a5ca58521a5c3346fb233345adc80fd3e2f542e2/psycopg-3.2.9-py3-none-any.whl";
        sha256 = "1dnkm33n75phjda008kbav0425k30rpcj232j4y15hmarpfdma01";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    django-registration = python.pkgs.buildPythonPackage rec {
      pname = "django-registration";
      version = "3.4";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/06/3a/455455a208cd38c7fececec136e0de4a848004a7dafe4d62e55566dcbbfe/django_registration-3.4-py3-none-any.whl";
        sha256 = "1l6xn7m4p4fgv1xiv42b35ihkywvrkjkw13kxd3lyyc9254dyxps";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    requests = python.pkgs.buildPythonPackage rec {
      pname = "requests";
      version = "2.32.4";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/7c/e4/56027c4a6b4ae70ca9de302488c5ca95ad4a39e190093d6c1a8ace08341b/requests-2.32.4-py3-none-any.whl";
        sha256 = "0b1bmhqv0xarifclr53icqwpsw1hk3l4w8230jrm0v9av8ybvfi7";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    rpds-py = python.pkgs.buildPythonPackage rec {
      pname = "rpds-py";
      version = "0.25.1";
      format = "wheel";

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/3e/03/5d0be919037178fff33a6672ffc0afa04ea1cfcb61afd4119d1b5280ff0f/rpds_py-0.25.1-cp313-cp313-manylinux_2_17_s390x.manylinux2014_s390x.whl";
        sha256 = "0yfgi9gb9xrvalxrzrhbh7ak0qfhi2kajw0zrxrmshgy4y2i4jjw";
      };

      # Disable checks
      doCheck = false;
      doInstallCheck = false;
    };

    django = self.buildPythonPackage rec {
      pname = "django";
      version = "5.2.6";
      format = "pyproject";
      doCheck = false;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/4c/8c/2a21594337250a171d45dda926caa96309d5136becd1f48017247f9cdea0/django-5.2.6.tar.gz";
        sha256 = "0yx82k8iilz8l6wkdvjcrz75i144lf211xybrrrks6b34wvh0pns";
      };
      nativeBuildInputs = with self; [setuptools];
      propagatedBuildInputs = with self; [
        asgiref
        sqlparse
      ];
      checkPhase = "echo 'Tests disabled for django'";
    };

    # Custom package from GitHub: https://github.com/dejacode/django-notifications-patched
    django-notifications-patched = self.buildPythonPackage rec {
      pname = "django-notifications-patched";
      version = "2.0.0";
      format = "setuptools";
      doCheck = false;

      src = pkgs.fetchFromGitHub {
        owner = "dejacode";
        repo = "django-notifications-patched";
        rev = "2.0.0";
        url = "https://github.com/dejacode/django-notifications-patched/archive/refs/tags/2.0.0.tar.gz";
        sha256 = "sha256-RDAp2PKWa2xA5ge25VqkmRm8HCYVS4/fq2xKc80LDX8=";
      };

      nativeBuildInputs = with self; [setuptools];
      checkPhase = "echo 'Tests disabled for django-notifications-patched'";
    };

    crontab = disableAllTests super.crontab {
      version = "1.0.5";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/d6/36/a255b6f5a2e22df03fd2b2f3088974b44b8c9e9407e26b44742cb7cfbf5b/crontab-1.0.5.tar.gz";
        sha256 = "1ma6ms0drlx6pj4q14jsjvkphwhl2zfjdyb9k0x7c6bjy2s023pq";
      };
      patches = [];
    };

    asgiref = disableAllTests super.asgiref {
      version = "3.9.1";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/90/61/0aa957eec22ff70b830b22ff91f825e70e1ef732c06666a805730f28b36b/asgiref-3.9.1.tar.gz";
        sha256 = "0hiiiq4xbm8mn9ykgp789pynqqhhkzyl5wj82vpya6324f16bax5";
      };
      patches = [];
    };

    setuptools = disableAllTests super.setuptools {
      version = "80.9.0";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/18/5d/3bf57dcd21979b887f014ea83c24ae194cfcd12b9e0fda66b957c69d1fca/setuptools-80.9.0.tar.gz";
        sha256 = "175iixi2h2jz8y2bpwziak360hvv43jfhipwzbdniryd5r04fszk";
      };
      patches = [];
    };

    wheel = disableAllTests super.wheel {
      version = "0.45.1";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/8a/98/2d9906746cdc6a6ef809ae6338005b3f21bb568bea3165cfc6a243fdc25c/wheel-0.45.1.tar.gz";
        sha256 = "0ab7ramncrii43smhvcidrbv4w4ndl80435214a7nl4qj6yil7k6";
      };
      patches = [];
    };

    typing-extensions = disableAllTests super.typing-extensions {
      version = "4.14.0";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/d1/bc/51647cd02527e87d05cb083ccc402f93e441606ff1f01739a62c8ad09ba5/typing_extensions-4.14.0.tar.gz";
        sha256 = "1x7fbkbpjj9xrsxfx6d38kccdr4a0hj17ip7v51an0igwf4bfxl6";
      };
      patches = [];
    };

    django-guardian = disableAllTests super.django-guardian {
      version = "3.0.3";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/30/c2/3ed43813dd7313f729dbaa829b4f9ed4a647530151f672cfb5f843c12edf/django_guardian-3.0.3.tar.gz";
        sha256 = "0v8ria6c0iirl1ck2xfzpcnf59629g8pdhghgh15mninv2sflnaf";
      };
      patches = [];
    };

    djangorestframework = disableAllTests super.djangorestframework {
      version = "3.16.1";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/8a/95/5376fe618646fde6899b3cdc85fd959716bb67542e273a76a80d9f326f27/djangorestframework-3.16.1.tar.gz";
        sha256 = "1xrzzjf048llw85vs3a2r7r4k07i594j8v66gnhx1khsid90js0n";
      };
      patches = [];
    };

    uritemplate = disableAllTests super.uritemplate {
      version = "4.1.1";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/d2/5a/4742fdba39cd02a56226815abfa72fe0aa81c33bed16ed045647d6000eba/uritemplate-4.1.1.tar.gz";
        sha256 = "1w14a775d92mx9pdhb5zimifpfr2lfcn0vfdpjagcy9vbkyfsij3";
      };
      patches = [];
    };

    redis = disableAllTests super.redis {
      version = "6.4.0";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/0d/d6/e8b92798a5bd67d659d51a18170e91c16ac3b59738d91894651ee255ed49/redis-6.4.0.tar.gz";
        sha256 = "047hbsy9rs44y81wdfbyl13vp0si6zsis9kbqf7f4i445clcf6xh";
      };
      patches = [];
    };

    model-bakery = disableAllTests super.model-bakery {
      version = "1.10.1";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/8f/4c/2fca1e79408308b8f0e71e687ca1e1d3ede450e257e2474e331261fdb106/model_bakery-1.10.1.tar.gz";
        sha256 = "0pmd0jmqbhvpyc52p42kmbn97lgg3zwaky5dcyr4p0izwfjssx0v";
      };
      patches = [];
    };

    fakeredis = disableAllTests super.fakeredis {
      version = "2.31.0";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/0b/10/c829c3475a26005ebf177057fdf54e2a29025ffc2232d02fb1ae8ac1de68/fakeredis-2.31.0.tar.gz";
        sha256 = "08ydbsc2v2i8zs5spa95lg2mlcc718cvj276z5phgn8gj3ksfhi9";
      };
      patches = [];
    };

    freezegun = disableAllTests super.freezegun {
      version = "1.5.2";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/c7/75/0455fa5029507a2150da59db4f165fbc458ff8bb1c4f4d7e8037a14ad421/freezegun-1.5.2.tar.gz";
        sha256 = "10aij0mdg4jmqpd396jlif0rahmbjnms661cw11bybf0z79f2jm5";
      };
      patches = [];
    };

    certifi = disableAllTests super.certifi {
      version = "2025.8.3";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/dc/67/960ebe6bf230a96cda2e0abcf73af550ec4f090005363542f0765df162e0/certifi-2025.8.3.tar.gz";
        sha256 = "01rlwvx3zi9bjfxvbspscdsal7ay8cj3k4kwmvin9mfyg1gi0r75";
      };
      patches = [];
    };

    cython = disableAllTests super.cython {
      version = "3.1.1";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/5b/d3/bb000603e46144db2e5055219bbddcf7ab3b10012fcb342695694fb88141/cython-3.1.1.tar.gz";
        sha256 = "15v36rp426zbgm4hrxn4i2028x3rf0n7jkc3acm17mb96r0wsp2h";
      };
      patches = [];
    };

    zipp = disableAllTests super.zipp {
      version = "3.22.0";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/12/b6/7b3d16792fdf94f146bed92be90b4eb4563569eca91513c8609aebf0c167/zipp-3.22.0.tar.gz";
        sha256 = "1rdcax7bi43xmm9la6mm0c8y6axvnwhisy6kpw3pbijbrv1jhbyx";
      };
      patches = [];
    };

    markdown = disableAllTests super.markdown {
      version = "3.8";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/2f/15/222b423b0b88689c266d9eac4e61396fe2cc53464459d6a37618ac863b24/markdown-3.8.tar.gz";
        sha256 = "0vww67gb1w890iyr6w3xkcira1b9wj0ynmninwj4np6zy1iixy3x";
      };
      patches = [];
    };

    oauthlib = disableAllTests super.oauthlib {
      version = "3.2.2";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/6d/fa/fbf4001037904031639e6bfbfc02badfc7e12f137a8afa254df6c4c8a670/oauthlib-3.2.2.tar.gz";
        sha256 = "066r7mimlpb5q1fr2f1z59l4jc89kv4h2kgkcifyqav6544w8ncq";
      };
      patches = [];
    };

    defusedxml = disableAllTests super.defusedxml {
      version = "0.7.1";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/0f/d5/c66da9b79e5bdb124974bfe172b4daf3c984ebd9c2a06e2b8a4dc7331c72/defusedxml-0.7.1.tar.gz";
        sha256 = "0s9ym98jrd819v4arv9gmcr6mgljhxd9q866sxi5p4c5n4nh7cqv";
      };
      patches = [];
    };

    funcparserlib = self.buildPythonPackage rec {
      pname = "funcparserlib";
      version = "0.3.6";
      format = "setuptools";
      doCheck = false;

      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/cb/f7/b4a59c3ccf67c0082546eaeb454da1a6610e924d2e7a2a21f337ecae7b40/funcparserlib-0.3.6.tar.gz";
        sha256 = "07f9cgjr3h4j2m67fhwapn8fja87vazl58zsj4yppf9y3an2x6dp";
      };

      # Original setpy.py: https://github.com/vlasovskikh/funcparserlib/blob/0.3.6/setup.py
      # funcparserlib version 0.3.6 uses use_2to3 which is no longer supported in modern setuptools.
      # Rewrite the problematic section completely
      postPatch = ''
              cat > setup.py << EOF
        # -*- coding: utf-8 -*-

        from setuptools import setup

        setup(
              name='funcparserlib',
              version='0.3.6',
              packages=['funcparserlib', 'funcparserlib.tests'],
              author='Andrey Vlasovskikh',
              author_email='andrey.vlasovskikh@gmail.com',
              description='Recursive descent parsing library based on functional '
                    'combinators',
              license='MIT',
              url='http://code.google.com/p/funcparserlib/',
        )
        EOF
      '';

      propagatedBuildInputs = with self; [];
      checkPhase = "echo 'Tests disabled for funcparserlib'";
    };

    click = disableAllTests super.click {
      version = "8.2.1";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/60/6c/8ca2efa64cf75a977a0d7fac081354553ebe483345c734fb6b6515d96bbc/click-8.2.1.tar.gz";
        sha256 = "00k2ck8g0f5ha26183wkkmnn7151npii7nx1smqx4s6r0p693i17";
      };
      patches = [];
    };

    packageurl-python = disableAllTests super.packageurl-python {
      version = "0.17.5";
      __intentionallyOverridingVersion = true;
    };

    jsonschema = disableAllTests super.jsonschema {
      version = "4.24.0";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/bf/d3/1cf5326b923a53515d8f3a2cd442e6d7e94fcc444716e879ea70a0ce3177/jsonschema-4.24.0.tar.gz";
        sha256 = "15nik6awrcj2y5nlnslabbpyq97cray08c1kh6ldzbhjxdlq0khb";
      };
      patches = [];
    };

    cyclonedx-python-lib = disableAllTests super.cyclonedx-python-lib {
      version = "10.2.0";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/3e/24/86a4949e59f8d79d42beef6041fd6ce842400addcec2f2a1bccb3208a5cd/cyclonedx_python_lib-10.2.0.tar.gz";
        sha256 = "1ralxk93zhyalg099bm6hxsqiisq8ha2rf7khjawz4bzhkd9lymn";
      };
      patches = [];
    };

    py-serializable = disableAllTests super.py-serializable {
      version = "2.0.0";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/f0/75/813967eae0542776314c6def33feac687642a193b9d5591c20684b2eafd8/py_serializable-2.0.0.tar.gz";
        sha256 = "1990yhn7a17j3z57r1ivlklgjmwngysk40h5y7d3376jswflkrp9";
      };
      patches = [];
    };

    smmap = disableAllTests super.smmap {
      version = "5.0.2";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/44/cd/a040c4b3119bbe532e5b0732286f805445375489fceaec1f48306068ee3b/smmap-5.0.2.tar.gz";
        sha256 = "1mcai5vf9bgz389y4sqgj6w22wn7zmc7m33y3j50ryjq76h6bsi6";
      };
      patches = [];
    };

    pydantic = disableAllTests super.pydantic {
      version = "2.11.5";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/f0/86/8ce9040065e8f924d642c58e4a344e33163a07f6b57f836d0d734e0ad3fb/pydantic-2.11.5.tar.gz";
        sha256 = "0ykv5aar0xjwfprdy31w8yrk2r6x5hf4130lpf5wwy6fs2rkv1bz";
      };
      patches = [];
    };

    setuptools-rust = disableAllTests super.setuptools-rust {
      version = "1.11.1";
      __intentionallyOverridingVersion = true;
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/e0/92/bf8589b1a2b6107cf9ec8daa9954c0b7620643fe1f37d31d75e572d995f5/setuptools_rust-1.11.1.tar.gz";
        sha256 = "1h3nbg1nlshzrqy7vz4q4g9wbz85dqkn6385p0ad7kjj48ww9avx";
      };
      patches = [];
    };

    django-axes = disableAllTests super.django-axes {
      version = "8.0.0";
      __intentionallyOverridingVersion = true;
    };

    sh = disableAllTests super.sh {};
    pytest-xdist = disableAllTests super.pytest-xdist {};
    altcha = disableAllTests super.altcha {};
    annotated-types = disableAllTests super.annotated-types {};
    async-timeout = disableAllTests super.async-timeout {};
    attrs = disableAllTests super.attrs {};
    bleach = disableAllTests super.bleach {};
    bleach-allowlist = disableAllTests super.bleach-allowlist {};
    boolean-py = disableAllTests super.boolean-py {};
    charset-normalizer = disableAllTests super.charset-normalizer {};
    confusable-homoglyphs = disableAllTests super.confusable-homoglyphs {};
    crispy-bootstrap5 = disableAllTests super.crispy-bootstrap5 {};
    deprecated = disableAllTests super.deprecated {};
    django-auth-ldap = disableAllTests super.django-auth-ldap {};
    django-crispy-forms = disableAllTests super.django-crispy-forms {};
    django-debug-toolbar = disableAllTests super.django-debug-toolbar {};
    django-environ = disableAllTests super.django-environ {};
    django-filter = disableAllTests super.django-filter {};
    django-otp = disableAllTests super.django-otp {};
    django-rq = disableAllTests super.django-rq {};
    doc8 = disableAllTests super.doc8 {};
    docutils = disableAllTests super.docutils {};
    drf-yasg = disableAllTests super.drf-yasg {};
    et-xmlfile = disableAllTests super.et-xmlfile {};
    gitdb = disableAllTests super.gitdb {};
    gitpython = disableAllTests super.gitpython {};
    gunicorn = disableAllTests super.gunicorn {};
    hatchling = disableAllTests super.hatchling {};
    inflection = disableAllTests super.inflection {};
    jinja2 = disableAllTests super.jinja2 {};
    jsonschema-specifications = disableAllTests super.jsonschema-specifications {};
    license-expression = disableAllTests super.license-expression {};
    markupsafe = disableAllTests super.markupsafe {};
    natsort = disableAllTests super.natsort {};
    numpy = disableAllTests super.numpy {};
    openpyxl = disableAllTests super.openpyxl {};
    packaging = disableAllTests super.packaging {};
    pandas = disableAllTests super.pandas {};
    pbr = disableAllTests super.pbr {};
    pillow = disableAllTests super.pillow {};
    platformdirs = disableAllTests super.platformdirs {};
    pyasn1 = disableAllTests super.pyasn1 {};
    pyasn1-modules = disableAllTests super.pyasn1-modules {};
    pycparser = disableAllTests super.pycparser {};
    pydantic-core = disableAllTests super.pydantic-core {};
    pyfakefs = disableAllTests super.pyfakefs {};
    pygments = disableAllTests super.pygments {};
    pyjwt = disableAllTests super.pyjwt {};
    pyparsing = disableAllTests super.pyparsing {};
    pypng = disableAllTests super.pypng {};
    pyrsistent = disableAllTests super.pyrsistent {};
    pytest-randomly = disableAllTests super.pytest-randomly {};
    pytest-regressions = disableAllTests super.pytest-regressions {};
    python3-openid = disableAllTests super.python3-openid {};
    python-dateutil = disableAllTests super.python-dateutil {};
    python-ldap = disableAllTests super.python-ldap {};
    python-mimeparse = disableAllTests super.python-mimeparse {};
    pytz = disableAllTests super.pytz {};
    pyyaml = disableAllTests super.pyyaml {};
    qrcode = disableAllTests super.qrcode {};
    referencing = disableAllTests super.referencing {};
    requests-oauthlib = disableAllTests super.requests-oauthlib {};
    restructuredtext-lint = disableAllTests super.restructuredtext-lint {};
    rq = disableAllTests super.rq {};
    ruff = disableAllTests super.ruff {};
    saneyaml = disableAllTests super.saneyaml {};
    semantic-version = disableAllTests super.semantic-version {};
    six = disableAllTests super.six {};
    sortedcontainers = disableAllTests super.sortedcontainers {};
    sqlparse = disableAllTests super.sqlparse {};
    stevedore = disableAllTests super.stevedore {};
    tblib = disableAllTests super.tblib {};
    toml = disableAllTests super.toml {};
    tomli = disableAllTests super.tomli {};
    tqdm = disableAllTests super.tqdm {};
    typing-inspection = disableAllTests super.typing-inspection {};
    urllib3 = disableAllTests super.urllib3 {};
    webencodings = disableAllTests super.webencodings {};
    wrapt = disableAllTests super.wrapt {};
    xlsxwriter = disableAllTests super.xlsxwriter {};

  };

  pythonWithOverlay = python.override {
    packageOverrides =
      self: super:
      let
        # Override buildPythonPackage to disable tests for ALL packages
        base = {
          buildPythonPackage =
            attrs:
            super.buildPythonPackage (
              attrs
              // {
                doCheck = false;
                doInstallCheck = false;
                doPytestCheck = false;
                pythonImportsCheck = [];
              }
            );
        };

        # Apply custom package overrides
        custom = pythonOverlay self super;
      in
      base // custom;
  };


  pythonApp = pythonWithOverlay.pkgs.buildPythonApplication {
    pname = "dejacode";
    version = "5.4.0";

    src = ./.;
    doCheck = false;
    doInstallCheck = false;
    doPytestCheck = false;
    pythonImportsCheck = [];

    format = "pyproject";

    nativeBuildInputs = with pythonWithOverlay.pkgs; [
      setuptools
      wheel
      pip
    ];


    # Specifies all Python dependencies required at runtime to ensure consistent overrides.
    propagatedBuildInputs = with pythonWithOverlay.pkgs; [
      maturin
      crontab
      django-filter
      natsort
      jsonschema
      freezegun
      docutils
      bleach-allowlist
      django-environ
      pyrsistent
      djangorestframework
      confusable-homoglyphs
      pygments
      async-timeout
      semantic-version
      markupsafe
      click
      sortedcontainers
      toml
      cyclonedx-python-lib
      six
      packaging
      clamd
      django-guardian
      altcha
      django-rest-hooks
      gitpython
      stevedore
      openpyxl
      qrcode
      django-rq
      bleach
      license-expression
      model-bakery
      mockldap
      pytz
      django-notifications-patched
      pyparsing
      funcparserlib
      typing-extensions
      smmap
      saneyaml
      requests-oauthlib
      oauthlib
      pyyaml
      et-xmlfile
      uritemplate
      xlsxwriter
      tblib
      django-crispy-forms
      defusedxml
      jsonschema-specifications
      doc8
      python3-openid
      redis
      django-axes
      pyasn1-modules
      swapper
      cython
      markdown
      py-serializable
      idna
      packageurl-python
      rpds-py
      rq
      django-auth-ldap
      typing-inspection
      urllib3
      certifi
      sqlparse
      wrapt
      boolean-py
      drf-yasg
      fakeredis
      inflection
      django-otp
      gitdb
      crispy-bootstrap5
      python-mimeparse
      attrs
      django-debug-toolbar
      jsonfield
      aboutcode-toolkit
      rq-scheduler
      zipp
      jinja2
      pyjwt
      gunicorn
      django-grappelli
      python-ldap
      ruff
      pydantic
      restructuredtext-lint
      referencing
      annotated-types
      pypng
      django-registration
      django-altcha
      python-dateutil
      pydantic-core
      pyasn1
      setuptools-rust
      requests
      pbr
      webencodings
      deprecated
      charset-normalizer
      psycopg
      asgiref
    ];

    meta = with pkgs.lib; {
      description = "Automate open source license compliance and ensure supply chain integrity";
      license = "AGPL-3.0-only";
      maintainers = ["AboutCode.org"];
      platforms = platforms.linux;
    };
  };

in
{
  # Default output is the Python application
  app = pythonApp;

  # Default to the application
  default = pythonApp;
}
