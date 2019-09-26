from rest_framework.views import APIView
from rest_framework.parsers import FileUploadParser

from django.shortcuts import get_object_or_404
from django.http import JsonResponse, Http404, HttpResponse
from django.utils.encoding import smart_str

from api.models import Project, Story, Intent, Utter
from api.parser import StoryParser, IntentParser, DomainParser
from api.utils.handlers import handle_uploaded_file
from api.utils import get_zipped_files
from api.decoder import decode_story_file, decode_intent_file
from api.utils.db_utils import bulk_update_unique

import os
from ruamel.yaml import YAML

class StoriesFile(APIView):
    """
    Receives a get request with a project id and returns
    a json response with the markdown string, containing
    all stories of the project, in the body.
    """

    def get(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        stories = Story.objects.filter(project=project)
        
        if not stories:
            raise Http404
        
        parser = StoryParser()
        markdown_str = ''

        for story in stories:
            markdown_str += parser.parse(story)
        
        return JsonResponse({'content': markdown_str})

    """
    Receives a put request with a project id and a Markdown file with story specs as arguments. Then parse and add this file into DB 
    """
    def put(self, request, project_id, format=None):
        project = get_object_or_404(Project, pk=project_id)

        # Handle file from request
        file_obj = request.data['file']
        
        with handle_uploaded_file(file_obj) as file_tmp:
            file_content = file_tmp.read().decode('utf-8')
            stories_dicts = decode_story_file(file_content)
            
            stories = []
            for story in stories_dicts:
                content = []
                for intent in story['intents']:
                    content.append({"id": Intent.objects.get(name=intent['intent']).id, "type": "intent" })

                    for utter in intent['utters']:
                        content.append({"id": Utter.objects.get(name=utter.replace("utter_","")).id, "type": "utter" })

                stories.append(Story(
                    name=story['story'],
                    content=content,
                    project=project
                ))

        bulk_update_unique(stories, 'name')

        return JsonResponse({'content': "File has been successfully uploaded"})



class IntentsFile(APIView):
    """
    Receives a get request with a project id and returns
    a json response with the markdown string, containing
    all intents of the project, in the body.
    """

    def get(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        intents = Intent.objects.filter(project=project)

        if not intents:
            raise Http404

        parser = IntentParser()
        markdown_str = ''

        for intent in intents:
            markdown_str += parser.parse(intent)

        return JsonResponse({'content': markdown_str})

    """
    Receives a put request with a project id and a Markdown file with intents specs as arguments. Then parse and add this file into DB 
    """
    def put(self, request, project_id, format=None):
        project = get_object_or_404(Project, pk=project_id)

        file_obj = request.data['file']
        with handle_uploaded_file(file_obj) as file_tmp:
            # Handle file from request
            file_content = file_tmp.read().decode('utf-8')
            
            intent_dicts = decode_intent_file(file_content)
            intents = []            
            for intent in intent_dicts:            
                intents.append(Intent(
                    name=intent['intent'].replace(" ","").replace("intent:", ""),
                    samples=intent['texts'],
                    project=project,
                ))

        bulk_update_unique(intents, 'name')
        return JsonResponse({'content': "File has been successfully uploaded"})


class UttersFile(APIView):
    """
    Receives a put request with a project id and a YML file with utter specs as arguments. Then parse and add this file into DB 
    """

    def put(self, request, project_id, format=None):
        project = get_object_or_404(Project, pk=project_id)

        # Handle file from request
        file_obj = request.data['file']
        file_tmp = handle_uploaded_file(file_obj)

        with handle_uploaded_file(file_obj) as file_tmp:
            # Handle yaml
            yaml=YAML(typ="safe")
            domain = yaml.load(file_tmp)
            
            utters_list = domain['templates']
            utters = []
            
            for utter_name in utters_list.keys():
                alternatives = [x['text'].split("\n\n") for x in utters_list[utter_name]]

                utters.append(Utter(
                    name= utter_name.strip().replace("utter_",""),
                    alternatives=[alternatives],
                    multiple_alternatives=True if len(alternatives) > 1 else False,
                    project=project
                ))
                

        bulk_update_unique(utters, 'name')
        return JsonResponse({'content': "File has been successfully uploaded"})

class DomainFile(APIView):
    """
    Receives a get request with a project id and returns
    a json response with markdown string, containing all
    domain content, in the body.
    """

    def get(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        parser = DomainParser()
        markdown_str = parser.parse(project)

        return JsonResponse({'content': markdown_str})

class ZipFile(APIView):
    def get(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        intents = Intent.objects.filter(project=project)
        stories = Story.objects.filter(project=project)

        # Intent parsing
        if not intents:
            raise Http404

        intent_parser = IntentParser()
        intent_markdown_str = ''

        for intent in intents:
            intent_markdown_str += intent_parser.parse(intent)

        # Story parsing
        if not stories:
            raise Http404
        
        stories_parser = StoryParser()
        stories_markdown_str = ''

        for story in stories:
            stories_markdown_str += stories_parser.parse(story)

        # Domain parsing
        domain_parser = DomainParser()
        domain_markdown_str = domain_parser.parse(project)

        coach_files = {
            'intents.md': intent_markdown_str, 
            'stories.md': stories_markdown_str, 
            'domain.yml': domain_markdown_str
        }

        file_name, file_path = get_zipped_files(project, coach_files)

        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='application/zip')
                response['Content-Disposition'] = 'attachment; filename={0}'.format(smart_str(file_name))

                return response
        else:
            raise Http404

