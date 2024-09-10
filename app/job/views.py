"""
Views for the job APIs.
"""
from rest_framework import viewsets, status, parsers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import get_object_or_404


import boto3
from botocore.exceptions import ClientError

from django.conf import settings
from django.db.models import Sum, Q

from knox.auth import TokenAuthentication

from app.schema import KnoxTokenScheme # needed, do not delete

from core.models import Job, Run, Budget
from job import serializers
from job.util import *
from .permissions import IsAdminUser, IsResearcher, IsEngineUser

import json
import os
import csv
import io
from django.http import HttpResponse



class JobViewSet(viewsets.ModelViewSet):
    """View for manage job APIs."""
    serializer_class = serializers.JobDetailSerializer
    queryset = Job.objects.all()
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Retrieve jobs for authenticated user."""
        if self.request.user.groups.filter(name='engine').exists():
            return self.queryset
        else:
            return self.queryset.filter(user=self.request.user).order_by('-created_at')

    def get_serializer_class(self):
        """Return the serializer class for request."""
        if self.action == 'list':
            return serializers.JobSerializer
        elif self.action == 'upload_script':
            return serializers.JobScriptSerializer
        elif self.action == "submit":
            return serializers.JobSubmitSerializer
        
        return self.serializer_class

    def perform_create(self, serializer):
        """Create a new job."""
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        # Check if the condition is true
        budget = Budget.objects.filter(user=request.user)[0]
        if not budget.review >= 1:
            return Response({'error': 'Insufficient budget'}, status=status.HTTP_400_BAD_REQUEST)

        # Condition is true, proceed with object creation
        return super().create(request, *args, **kwargs)

    def list(self, request):
        queryset = self.get_queryset()
        serializer = serializers.JobSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        item = get_object_or_404(self.queryset, pk=pk)
        serializer = serializers.JobDetailSerializer(item)
        return Response(serializer.data)

    @action(methods=['POST'], detail=True, url_path='upload-script')
    def upload_script(self, request, pk=None):
        """Upload a script to a job"""
        job = self.get_object()
        serializer = self.get_serializer(
            job,
            data=request.data
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                serializer.data,
                status=status.HTTP_200_OK
            )
        
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    
class RunViewSet(viewsets.ModelViewSet):
    """View for manage run APIs."""
    serializer_class = serializers.RunDetailSerializer
    queryset = Run.objects.all()
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    lookup_field = ('run_id')

    def get_queryset(self):
        """Retrieve jobs for authenticated user."""
        if self.request.user.groups.filter(name='engine').exists():
            return self.queryset.filter(job=self.kwargs['jobs_pk']).order_by('-created_at')
        else:
            return Run.objects.filter(job=self.kwargs['jobs_pk'], job__user=self.request.user).order_by('-id')

    def get_serializer_class(self):
        """Return the serializer class for request."""
        if self.action == 'list':
            return serializers.RunSerializer
        
        return self.serializer_class
    
    def partial_update(self, request, *args, **kwargs):
        instance = self.queryset.get(job=kwargs.get('jobs_pk'),run_id=kwargs.get('run_id'))
        serializer = self.serializer_class(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        #serializer.validated_data['cost'] = compute_cost(request.data['epsilon'], instance.job.max_epsilon)
        # send signal to update_review_budget

        serializer.save()
        return Response(serializer.data)

    def retrieve(self, request, jobs_pk=None, run_id=None)   :
        job = get_object_or_404(Job, id=jobs_pk)
        item = get_object_or_404(self.queryset, job=job, run_id=run_id)
        serializer = serializers.RunDetailSerializer(item)
        return Response(serializer.data) 
    
    @action(methods=['GET'], detail=True, url_path='get-csv-results')
    def get_csv_results(self, request, jobs_pk=None, run_id=None):
        # Set up S3 client
        s3 = boto3.client('s3', aws_access_key_id=settings.AWS_ACCESS_KEY_ID, aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY)

        # Set up S3 bucket and file details
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        file_key = os.path.join('submissions',jobs_pk,f'sanitized_output_{run_id}.csv')

        print(file_key)
        # Retrieve the file from S3
        try:
            response = s3.get_object(Bucket=bucket_name, Key=file_key)
            file_content = response['Body'].read().decode('utf-8')  # Decode the CSV file content
        except ClientError as e:
            return HttpResponse(f"Error retrieving file: {str(e)}", status=500)

        # Set the response headers to indicate a CSV file download
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_key)}"'

        # Write the CSV file content to the response
        writer = csv.writer(response)
        for line in file_content.splitlines():
            writer.writerow(line.split(','))

        return response


    @action(methods=['POST'], detail=True, url_path='refine')
    def refine(self, request, jobs_pk=None, run_id=None):
        """Endpoint that accepts refined epsilon values for statistics"""
        job = get_object_or_404(Job, id=jobs_pk)
    
        # Validate payload
        serializer = serializers.RefineSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        refined_statistics = serializer.validated_data['refined']

        # Compute cost
        cost = compute_cost(refined_statistics)
        print(f"cost={cost}")

        # Check budget
        budget = Budget.objects.filter(user=request.user)[0]
        if budget.review < cost:
            return Response({'error': 'Insufficient budget'}, status=status.HTTP_403_FORBIDDEN)
        print(f"review_budget = {budget.review}")
        
        # Create new run
        run = Run.objects.create(job=job)

        # Trigger sanitizer
        response = trigger_sanitizer(run, refined_statistics)
        print(response)
        # Charge user
        if response.status_code == status.HTTP_200_OK:
            Budget.objects.filter(user=request.user)[0].charge_review_budget(cost)

        return response
    

    @action(methods=['POST'], detail=True, url_path='release')
    def release(self, request, jobs_pk=None, run_id=None):
        """Endpoint that releases results."""
        # TODO: Validate payload
        released_ids = request.data['analysis_ids']
        print(released_ids)

        # Set up S3 client
        s3 = boto3.client('s3', aws_access_key_id=settings.AWS_ACCESS_KEY_ID, aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY)

        # Set up S3 bucket and file details
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        file_key = os.path.join('submissions',jobs_pk,f'sanitized_output_{run_id}.csv')
        print(file_key)
        
        # Retrieve the file from S3
        try:
            response = s3.get_object(Bucket=bucket_name, Key=file_key)
            file_content = response['Body'].read().decode('utf-8')  # Decode the CSV file content
        except ClientError as e:
            return HttpResponse(f"Error retrieving file: {str(e)}", status=500)

        # Set the response headers to indicate a CSV file download
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_key)}"'

        # Compute cost to release and generate CSV content 
        output_buffer = io.StringIO()
        writer = csv.writer(output_buffer)
        line_num = 1
        cost = 0 
        for csv_line in file_content.splitlines():
            # Header
            if line_num == 1:
                col_list = csv_line.split(',')
                analysis_id_index = col_list.index("analysis_id")
                epsilon_index = col_list.index("epsilon")
                writer.writerow(csv_line.split(','))
            else:
                value_list = csv_line.split(',')
                analysis_id = int(value_list[analysis_id_index])
                if analysis_id in released_ids: 
                    writer.writerow(csv_line.split(','))
                    epsilon = float(value_list[epsilon_index])
                    cost = cost + epsilon
            line_num = line_num + 1

        # Enough release budget?
        budget = get_object_or_404(Budget, user=request.user)
        print(cost)
        if budget.release < cost:
            return Response({'error': 'Insufficient budget'}, status=status.HTTP_403_FORBIDDEN)

        # Write released CSV to S3  
        output_file_key = os.path.join('submissions',jobs_pk,f'released_output_{run_id}.csv')
        upload_csv_to_s3(output_buffer, output_file_key)
        
        # Charge user
        Budget.objects.filter(user=request.user)[0].charge_release_budget(cost)

        # Update run status to "released"
        run = get_object_or_404(self.queryset, job=jobs_pk, run_id=run_id)
        run.status = {'ok': True, 'info': 'released', 'errormsg': None}
        run.save() 

        # Update job status to "released"
        job = get_object_or_404(Job, id=jobs_pk)
        job.status = {'ok': True, 'info': 'released', 'errormsg': None}
        job.save() 
              
        return response 
    

    @action(methods=['GET'], detail=True, url_path='get-released-csv-results')
    def get_released_csv_results(self, request, jobs_pk=None, run_id=None):  
        """Endpoint that returns results that have already been released."""
        # Set up S3 client
        s3 = boto3.client('s3', aws_access_key_id=settings.AWS_ACCESS_KEY_ID, aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY)

        # Set up S3 bucket and file details
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        file_key = os.path.join('submissions',jobs_pk,f'released_output_{run_id}.csv')
        print(file_key)

        # Retrieve the file from S3
        try:
            response = s3.get_object(Bucket=bucket_name, Key=file_key)
            file_content = response['Body'].read().decode('utf-8')  # Decode the CSV file content
        except ClientError as e:
            return HttpResponse(f"Error retrieving file: {str(e)}", status=500)

        # Set the response headers to indicate a CSV file download
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_key)}"'

        # Write the CSV file content to the response
        writer = csv.writer(response)
        for line in file_content.splitlines():
            writer.writerow(line.split(','))
        return response
    

    @action(methods=['GET'], detail=True, url_path='get-analyses')
    def get_analyses(self, request, jobs_pk=None, run_id=None):  
        """Endpoint that returns all analyses for a given run and their total cost."""
        # Set up S3 client
        s3 = boto3.client('s3', aws_access_key_id=settings.AWS_ACCESS_KEY_ID, aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY)

        # Set up S3 bucket and file details
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        file_key = os.path.join('submissions',jobs_pk,f'sanitized_output_{run_id}.csv')
        print(file_key)

        # Retrieve the file from S3
        try:
            response = s3.get_object(Bucket=bucket_name, Key=file_key)
            file_content = response['Body'].read().decode('utf-8')  # Decode the CSV file content
        except ClientError as e:
            return HttpResponse(f"Error retrieving file: {str(e)}", status=500)
        
        # Compute cost (epsilon sum) by analysis_id (and keep track of analysis_name)
        analyses_dict = {}
        line_num = 1

        for csv_line in file_content.splitlines():
            if line_num == 1: 
                col_list = csv_line.split(',')
                analysis_id_index = col_list.index("analysis_id")
                analysis_name_index = col_list.index("analysis_name")
                epsilon_index = col_list.index("epsilon")
            else: 
                value_list = csv_line.split(',')
                analysis_id = value_list[analysis_id_index]
                analysis_name = value_list[analysis_name_index]
                epsilon = float(value_list[epsilon_index])

                if analysis_id not in analyses_dict: 
                    analyses_dict[analysis_id] = {
                        "epsilon": epsilon, 
                        "analysis_name": analysis_name
                    }
                else: 
                    analyses_dict[analysis_id]['epsilon'] += epsilon 
            line_num = line_num + 1

        # Format as list of dictionaries 
        analyses_list = [
            {
                "analysis_id": key, 
                "analysis_name": value['analysis_name'],
                "epsilon_sum": value['epsilon'], 
            } 
            for key, value in analyses_dict.items()
        ]
        
        return Response(analyses_list, status=status.HTTP_200_OK)
