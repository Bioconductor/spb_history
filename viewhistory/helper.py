from bioconductor.config import BUILD_NODES

def sort_helper(b1, b2):
    os_order = {'Linux': 0, 'Windows': 1, 'Mac': 2}
    word = b1.os.split(" ")[0]
    word2 = b2.os.split(" ")[0]
    return(cmp(os_order[word], os_order[word2]))

def re_sort(builds):
    return(sorted(builds, cmp=sort_helper))


def get_message(build, build_phase):
    messages = build.message_set.filter(build_phase=build_phase)
    message = ""
    for m in messages:
        message += m.body
    return(message)


def get_messages(builds):
    phases = ['building', 'buildingbin', 'checking',
      'post_processing', 'preprocessing']
    for build in builds:
        build.foo = "kfhgkfh22"
        setattr(build, "bar", "lalalal")
        for phase in phases:
            attr_name = "%s_message" % phase
            message = get_message(build, phase)
            setattr(build, attr_name, message)
            #print("[%s]build.%s is \n%s" % (build.builder_id, attr_name, getattr(build, attr_name)))


## FIXME there must be a less hardcodey way to do this
def filter_out_wrong_versions(builds, job):
    r_ver = job.r_version
    bioc_version = job.bioc_version

    nodes = []

    # FIXME get this info from a central source (config.yaml)
    if (r_ver == "4.5"):
        if bioc_version == "3.22":
            nodes = BUILD_NODES
    if (r_ver == "4.5"):
        if bioc_version == "3.21":
            nodes = ["nebbiolo1"]
    if (r_ver == "4.4"):
        if bioc_version == "3.20":
            nodes = ["teran2", "lconway"]
    if (r_ver == "4.4"):
        if bioc_version == "3.19":
            nodes = ["nebbiolo1"]
    if (r_ver == "4.3"):
        if bioc_version == "3.18":
            nodes = ["nebbiolo2", "lconway"]
    if (r_ver == "4.3"):
        if bioc_version == "3.17":
            nodes = ["nebbiolo1", "merida1"]
    if (r_ver == "4.2"):
        if bioc_version == "3.16":
            nodes = ["nebbiolo1"]
    if (r_ver == "4.2"):
        if bioc_version == "3.15":
            nodes = ["nebbiolo1", "merida1"]
    if (r_ver == "4.1"):
        if bioc_version == "3.14":
            nodes = ["nebbiolo2", "tokay2", "machv2"]
    if (r_ver == "4.1"):
        if bioc_version == "3.13":
            nodes = ["malbec2", "tokay2", "machv2"]
    if (r_ver == "4.0"):
        if bioc_version == "3.12":
            nodes = ["malbec1", "tokay1", "merida1"]
        elif bioc_version == "3.11":
            nodes =  ["malbec2", "tokay2"]
    if (r_ver == "3.6"):
        if bioc_version == "3.10":
            nodes = ["malbec1", "tokay1", "merida1"]
        elif bioc_version == "3.9":
            nodes = ["malbec2", "tokay2", "celaya2"]
    if (r_ver == "3.5"):
        if bioc_version == "3.8":
            nodes = ["malbec1", "tokay1", "merida1"]
        elif bioc_version == "3.7":
            nodes = ["malbec2", "tokay2", "merida2"]
    if (r_ver == "3.4"):
        if bioc_version == "3.6":
            nodes = ["malbec1", "tokay1", "veracruz1"]
        elif bioc_version == "3.5":
            nodes = ["malbec2", "tokay2", "toluca2", "veracruz2"]
    if (r_ver == "3.3"):
        if bioc_version == "3.4":
            nodes = ["zin1", "moscato1", "morelia"]
        elif bioc_version == "3.3":
            nodes = ["zin2", "moscato2", "oaxaca"]
    if (r_ver == "3.2"):
        if bioc_version == "3.1":
            nodes = BUILD_NODES
        if bioc_version == "3.2":
            nodes = ["linux1.bioconductor.org", "perceval", "windows1.bioconductor.org", "oaxaca"]
    if (r_ver == "3.1"):
        if bioc_version == "3.0":
            nodes = ["zin1", "perceval", "moscato1", "oaxaca"]
        if bioc_version == "2.14":
            nodes = ["zin2", "petty", "moscato2"]
    if (r_ver == "2.16" or r_ver == "3.0"):
        if bioc_version == "2.12":
            nodes = ['george2', 'petty', 'moscato2']
        if bioc_version == "2.13":
            nodes = ["zin1", "perceval", "moscato1"]
    if (r_ver == "2.15"):
        if (bioc_version == "2.11"):
            nodes = ["lamb1", "moscato1", "perceval"]
        if (bioc_version == "2.10"):
            nodes = ["lamb2", "moscato2", "petty"]
    ## keep old stuff here so build history continues to work

    if (len(nodes) == 0):
        raise Exception("Don't know the build nodes for R-%s (BioC %s)" % (r_ver, bioc_version))

    ret = []
    for build in builds:
        if build.builder_id in nodes:
            ret.append(build)
    return (ret)
