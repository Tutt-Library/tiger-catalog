"""Custom Islandora Repository Ingester for Colorado College, extends 
BIBCAT MODS Ingester."""
__author__ = "Jeremy Nelson"

import click
import datetime
import logging
import os
import rdflib
import requests
import sys
import xml.etree.ElementTree as etree

TIGER_BASE = os.path.abspath(
    os.path.split(
        os.path.dirname(__file__))[0])
sys.path.append(TIGER_BASE)
import bibcat.ingesters.mods as mods_ingester

NS_MGR = mods_ingester.NS_MGR
NS_MGR.bind("pcdm", rdflib.Namespace("http://pcdm.org/models#"))

FEDORA_NS = {
    "fedora_access": "http://www.fedora.info/definitions/1/0/access/",
    "fedora_model": "info:fedora/fedora-system:def/model#",
    "rdf": str(NS_MGR.rdf)
}
class IslandoraIngester(mods_ingester.MODSIngester):

    def __init__(self, **kwargs):
        """Takes kwargs and initialize instance of IslandoraIngester"""
        if not 'rules' in kwargs:
            kwargs['rules'] = ['cc-mods-bf.ttl']
        kwargs["base_url"] = "https://catalog.coloradocollege.edu/"
        self.fedora_base = kwargs.pop("repository_url")
        self.ingested_pids = []
        self.ri_search = "{}/risearch".format(self.fedora_base)
        self.rest_url = "{}/objects/".format(self.fedora_base)
        self.auth = (kwargs.pop("user"), kwargs.pop("password"))
        super(IslandoraIngester, self).__init__(**kwargs)

    def __add_pid_identifier__(self, pid, graph=None):
        """Adds PID as a Blank BF Identifier

        Args:
            pid(str): PID of Object
            graph(rdflib.Graph): Graph to add PID, default is 
                working ingester graph
        """
        if graph is None:
            graph = self.graph
        local_bnode = rdflib.BNode()
        graph.add((local_bnode, 
            NS_MGR.rdf.type, 
            NS_MGR.bf.Local))
        graph.add((local_bnode,
            NS_MGR.rdf.value,
            rdflib.Literal(pid)))
        graph.add((local_bnode,
            NS_MGR.rdfs.label,
            rdflib.Literal("Fedora 3.8 PID", lang="en")))
        return local_bnode

    def __add_pdf_ds_to_item__(self, pdf_pid, pdf_datastream, instance_iri):
        """Method takes an existing PDF Datastream and either adds additional
        BF metadata to the Instance and Item if the Instance's Work is
        a Text or creates a new Instance and Item and creates a relationship
        between the original Instance. 
 
        Args:
            pid_pid(str): PID of Datastream's Fedora Object 
            pdf_datastream(etree.Element): Element of PDF Datastream
            instance_iri(rdflib.URIRef): IRI of BIBFRAME Instance
        """
        text_work = self.graph.value(predicate=NS_MGR.rdf.type,
            object=NS_MGR.bf.Text)
        if text_work is None:
            # Adds new instance
            original_instance = instance_iri
            instance_iri = self.__generate_uri__()
            self.add_admin_metadata(instance_iri)
            self.graph.add((instance_iri, NS_MGR.rdf.type, NS_MGR.bf.Instance))
            self.graph.add((instance_iri, NS_MGR.bf.supplementTo, original_instance))
            # Use the pdf_datastream label as a Instance Title
            instance_title = rdflib.BNode()
            self.graph.add((instance_iri, NS_MGR.bf.title, instance_title))
            self.graph.add((instance_title, NS_MGR.rdf.type, NS_MGR.bf.InstanceTitle))
            self.graph.add(
                (instance_title, 
                 NS_MGR.bf.mainTitle, 
                 rdflib.Literal(pdf_datastream.get("LABEL"))))
            item_iri = self.__generate_uri__()
            self.add_admin_metadata(item_iri)
            self.graph.add((item_iri, NS_MGR.rdf.type, NS_MGR.bf.Item))
            self.graph.add((item_iri, NS_MGR.itemOf, instance_iri))
            institution = next(self.rules_graph.objects(predicate=NS_MGR.bf.heldBy))
            self.graph.add((item_iri, NS_MGR.bf.heldBy, institution))
        else: 
            item_iri = self.graph.value(predicate=NS_MGR.bf.itemOf,
                object=instance_iri)
       # Adds Encoding Format 
        encoding_format = rdflib.BNode()
        self.graph.add(
            (encoding_format, NS_MGR.rdf.type, NS_MGR.bf.EncodingFormat))
        self.graph.add(
            (instance_iri, NS_MGR.bf.digitalCharacteristic, encoding_format))
        self.graph.add((
            encoding_format, 
            NS_MGR.rdf.value, 
            rdflib.Literal(pdf_datastream.get("mimeType"))))
        # Adds PID as local identifier to the item
        

        
        
            

    def __get_content_model__(self, rels_ext):
        """Retrieves content models and filters out and
        returns.

        Args:
            rels_ext(etree.XML): XML doc of RELS-EXT
        """
        # Variable processing depending on content model
        has_models = rels_ext.findall(
            "rdf:Description/fedora_model:hasModel", 
            FEDORA_NS)
        if len(has_models) < 1:
            raise ValueError("{} missing content model in RELS-EXT".format(
                pid))
        for i, row in enumerate(has_models):
            content_model = row.get(
                "{{{0}}}resource".format(NS_MGR.rdf))
            if content_model.startswith(
                "info:fedora/fedora-system:FedoraObject-3.0"):
                has_models.pop(i)
        if len(has_models) == 1:
            return has_models[0].get(
                "{{{0}}}resource".format(NS_MGR.rdf))

    def __get_datastreams__(self, pid):
        """Method returns XML doc of Datastreams

        Args:
            pid(str): PID of Fedora Object

        Returns:
            etree.Element: XML Document of result listing
        """
        ds_url = "{0}{1}/datastreams?format=xml".format(
            self.rest_url,
            pid)
        datastreams_result = requests.get(
            ds_url, 
            auth=self.auth)
        if datastreams_result.status_code > 399:
             raise ValueError(
                "Cannot retrieve datastream listing for {}".format(pid)) 
        ds_doc = etree.XML(datastreams_result.text)
        return ds_doc



    def __get_label__(self, pid):
        """Retrieves label for a PID using the REST API"""
        object_url = "{}{}?format=xml".format(self.rest_url, pid)
        result = requests.get(object_url,
            auth=self.auth)
        if result.status_code < 400:
            object_profile = etree.XML(result.text)
            label = object_profile.find(
                "fedora_access:objLabel", 
                FEDORA_NS)
            if label is not None:
                return rdflib.Literal(label.text)

    def __get_instance_iri__(self, pid):
        """Attempts to retrieve instance IRI based on the PID

        Args:
            pid: Fedora Object PID

        Returns:
            rdflib.URIRef: IRI of Instance or None if PID not found
        """
        sparql = NS_MGR.prefix() + """
        SELECT ?instance
        WHERE {{
            ?instance bf:identifiedBy ?pid .
            ?pid a bf:Local .
            ?pid rdf:value "{0}" .
        }}""".format(pid)
        instance_result = requests.post(
            self.triplestore_url,
            data={"query": sparql,
                  "format": "json"})
        if instance_result.status_code > 399:
            raise ValueError(
                "Could not retrieve instance IRI w/PID {}".format(pid))
        bindings = instance_result.json().get('results').get('bindings')
        if len(bindings) < 0:
            return
        elif len(bindings) == 1:
            return rdflib.URIRef(bindings[0]['instance']['value'])
            
            

    def __guess_instance_class__(self, work_classes):
        """Attempts to guess additional instanc classes for the Fedora Object

        Args:
            work_classes(list): List of BF Work Classes
        """
        instance_classes = []
        return instance_classes
       
    def __guess_work_class__(self, instance_iri, content_model):
        """Attempts to guess additional work classes for the Fedora Object
        
        Args:
            content_model(str): Islandora Content Model
        Returns:
            List of BF Classes
        """
        bf_work_classes = []
        if content_model.startswith("info:fedora/islandora:sp_pdf"):
            bf_work_classes.append(NS_MGR.bf.Text)
        genre_query = NS_MGR.prefix() +"""
        SELECT ?value
        WHERE {{
            <{0}> bf:genreForm ?genre .
            ?genre rdf:value ?value .
        }}""".format(instance_iri)
        for row in self.graph.query(genre_query):
            genre = str(row[0])
            #! Move to RDF rule?
            if genre.startswith("interview"):
                bf_work_classes.append(NS_MGR.bf.Audio)
        return bf_work_classes 

    def __mods_to_bibframe__(self, pid):
        """Downloads MODS based on the PID and runs the transformation 
        to BIBFRAME.

        Args:
            pid: PID of Fedora OBject

        Returns:
            rdflib.URIRef: URI of Instance
        """
        mods_url = "{0}{1}/datastreams/MODS/content".format(
                    self.rest_url,
                    pid)
        mods_result = requests.get(mods_url, auth=self.auth)
        if mods_result.status_code == 404:
            # Tries to retrieve first and use MODS Datastreams of 
            # any related Fedora Objects
            sparql = """SELECT DISTINCT ?s
WHERE {{
   ?s <fedora-rels-ext:isConstituentOf> <info:fedora/{0}> .
}}""".format(pid)
            constituents_response = requests.post(
                self.ri_search,
                data={"type": "tuples",
                      "lang": "sparql",
                      "format": "json",
                      "query": sparql},
                auth=self.auth)
            constituents = constituents_response.json().get('results')
            for row in constituents:
                child_pid = row.get('s').split("/")[-1]
                child_ds_doc = self.__get_datastreams__(child_pid)
                mods_ds = child_ds_doc.find(
                    """fedora_access:datastream[@disd="MODS"]""")
                if mods_ds is not None:
                    return self.__mods_to_bibframe__(child_pid)
        else:   
            mods_xml = etree.XML(mods_result.text)
        self.transform(mods_xml)
        instance_uri = self.graph.value(
            predicate=NS_MGR.rdf.type,
            object=NS_MGR.bf.Instance)
        if instance_uri is None:
            raise ValueError("Unable to extract Instance from Graph")
        return instance_uri
            
                

    def ingest_collection(self, pid):
        """Takes a Fedora 3.8 PID, retrieves all children and ingests into
        triplestore 

        Args:
            pid: PID of Collection
        """
        collection_graph = mods_ingester.new_graph()
        collection_iri = self.__generate_uri__()
        for type_of in [NS_MGR.pcdm.Collection, NS_MGR.bf.Work]:
            collection_graph.add((collection_iri,
				  NS_MGR.rdf.type,
				  type_of))
        # Adds PID as a bf:Local identifier for the collection
        local_bnode = self.__add_pid_identifier__(pid, collection_graph)
        collection_graph.add((collection_iri,
            NS_MGR.bf.identifiedBy,
            local_bnode))
        collection_label = self.__get_label__(pid)
        collection_graph.add(
            (collection_iri, NS_MGR.rdfs.label, collection_label))
        sparql = MEMBER_OF_SPARQL.format(pid)
        children_response = requests.post(
            self.ri_search,
            data={"type": "tuples",
                  "lang": "sparql",
                  "format": "json",
                  "query": sparql},
            auth=self.auth)
        if children_response.status_code < 400:
            children = children_response.json().get('results')
            for i,row in enumerate(children):
                uri = row.get('s')
                child_pid = uri.split("/")[-1]
                # Adds Child Instance IRI as a part of the Collection
                child_iri = self.process_pid(child_pid)
                # Parent
                collection_graph.add(
                    (collection_iri, NS_MGR.bf.hasPart, child_iri))
                if not i%10:
                    print(".", end="")
        collection_result = requests.post(
            self.triplestore_url,
            data=collection_graph.serialize(format='turtle'),
            headers={"Content-Type": "text/turtle"})
        return collection_iri

    def ingest_compound(self, pid, instance_iri):
        """Handles Complex Compound Objects

        Args:
            instance_uri(rdflib.URIRef): IRI of base instance
        """
        sparql = """SELECT DISTINCT ?s
WHERE {{
   ?s <fedora-rels-ext:isConstituentOf> <info:fedora/{0}> .
}}""".format(pid)
        constituents_response = requests.post(
            self.ri_search,
            data={"type": "tuples",
                  "lang": "sparql",
                  "format": "json",
                  "query": sparql},
            auth=self.auth)
        if constituents_response.status_code > 399:
            raise ValueError("Ingesting Compound {} Failed".format(
                pid))
        constituents = constituents_response.json().get('results')
        for row in constituents:
            child_pid = row.get('s').split("/")[-1]
            child_ds_doc = self.__get_datastreams__(child_pid)
            child_datastreams = child_ds_doc.find(
                "fedora_access:datastream", 
                FEDORA_NS)
            pdf_datastream = child_datastreams.find(
                "fedora_access:datastream[@mimeType='application/pdf']",
                FEDORA_NS)
            if pdf_datastream is not None:
                self.__add_pdf_ds_to_item__(child_pid, 
                    pdf_datastream, 
                    instance_iri)
            self.ingested_pids.append(child_pid)
        self.add_to_triplestore()
        return instance_iri
      

    def process_pid(self, pid):
        """Takes a PID, retrieves RELS-EXT and MODS and runs the ingester 
        MODS rules on MODS.

        Args:
            pid: PID of Fedora Object
        Returns:
            rdflib.URIRef of PID Instance
        """ 
        if pid in self.ingested_pids:
            return self.__get_instance_iri__(pid)
        # Retrieves RELS-EXT XML
        rels_ext_url = "{0}{1}/datastreams/RELS-EXT/content".format(
            self.rest_url,
            pid)
        rels_ext_result = requests.get(rels_ext_url, auth=self.auth)
        rels_ext = etree.XML(rels_ext_result.text)
        content_model = self.__get_content_model__(rels_ext)
        # If a collection model, returns result of calling ingest_collection
        if content_model.startswith('info:fedora/islandora:collectionCModel'):
            return self.ingest_collection(pid)
        # Retrieves MODS for Fedora Object and performs MODS to BIBFRAME
        # transformation
        instance_uri = self.__mods_to_bibframe__(pid)
        # Builds supporting Instances and Works if a compound object
        if content_model.startswith("info:fedora/islandora:compoundCModel"):
            return self.ingest_compound(pid, instance_uri)
        # Adds PID as Local Identifier
        local_bnode = self.__add_pid_identifier__(pid)
        self.graph.add((instance_uri, NS_MGR.bf.identifiedBy, local_bnode)) 
        # Matches best BIBFRAME Work Class 
        addl_work_classes = self.__guess_work_class__(instance_uri, content_model)
        work_bnode = self.graph.value(subject=instance_uri,
            predicate=NS_MGR.bf.instanceOf)
        if work_bnode is None:
            work_bnode = rdflib.BNode()
            self.graph.add((instance_uri, NS_MGR.bf.instanceOf, work_bnode))
        for work_class in addl_work_classes:
            self.graph.add(
                (work_bnode,
                 NS_MGR.rdf.type,
                 work_class))
        # Matches best BIBFRAME Instance Class
        addl_instance_classes = self.__guess_instance_class__(rels_ext)
        for instance_class in addl_instance_classes:
            self.graph.add(
                (instance_uri, 
                 NS_MGR.rdf.type, 
                 addl_instance_class))
        self.add_to_triplestore()
        return instance_uri

        


# SPARQL Templates        
MEMBER_OF_SPARQL = """SELECT DISTINCT ?s
WHERE {{
  ?s <fedora-rels-ext:isMemberOfCollection> <info:fedora/{}> .
}}"""

# Command-line handler
@click.command()
@click.option("--root", default="coccc:root", help="CC Root PID")
@click.option("--user", help="Fedora 3.8 User")
@click.option("--pwd", help="Fedora 3.8 Password")
@click.option("--fedora_base", help="Fedora 3.8 Base URL")
@click.option("--triplestore", 
    default="http://localhost:9999/blazegraph/sparql",
    help="Triplestore URL, uses Blazegraph default URL")
def run_ingester(root, user, pwd, fedora_base, triplestore):
    """Function runs ingester from the command line """
    logging.getLogger("requests").setLevel(logging.CRITICAL)
    start = datetime.datetime.utcnow()
    print("Start CC Islandora ingestion into BF 2.0 triplestore at {}".format(
        start.isoformat()))
    ingester = IslandoraIngester(
        repository_url=fedora_base,
        triplestore_url=triplestore,
        user=user,
        password=pwd)
    ingester.ingest_collection(root)
    end = datetime.datetime.utcnow()
    print("Finished CC Islandora ingestion at {}, total time={} minutes".format(
        end.isoformat(),
        (end-start).seconds / 60.0))
        
     
if __name__ == '__main__':
    run_ingester()